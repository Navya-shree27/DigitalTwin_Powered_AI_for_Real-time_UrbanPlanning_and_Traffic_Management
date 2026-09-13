"""
backend/api/routes_simulation.py
──────────────────────────────────
API routes for simulation management.

Endpoints
─────────
  POST /api/scenarios                       — create a new scenario
  GET  /api/scenarios                       — list all scenarios
  GET  /api/scenarios/{scenario_id}         — get a single scenario
  POST /api/scenarios/{scenario_id}/simulate — run baseline simulation
  GET  /api/scenarios/{scenario_id}/runs    — list all runs for a scenario
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.db_connector import get_db
from backend.models.schema import Issue, Proposal, Scenario, SimulationRun, ValidationResult

log = logging.getLogger("routes_simulation")
router = APIRouter(prefix="/api/scenarios", tags=["Simulation"])

ROOT = Path(__file__).resolve().parent.parent.parent


# ── Request / Response models ─────────────────────────────────────────────────

class ScenarioCreate(BaseModel):
    name: str = Field(..., description="Human-readable scenario name")
    city: str = Field(
        default="Davanagere, Karnataka, India",
        description="Place name or city for OSM data download"
    )
    description: str = Field(default="")
    force_rebuild: bool = Field(default=False, description="Force re-download of OSM data")


class SimulateRequest(BaseModel):
    engine: str = Field(default="sumo", description="synthetic | sumo | cityflow")
    duration_s: int = Field(default=300, ge=60, le=86400)
    seed: int = Field(default=42)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_network_meta() -> dict:
    meta_path = ROOT / "data" / "processed" / "network" / "network_meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}


def _write_progress(scenario_id: int, data: dict):
    """Write or update simulation progress for a scenario."""
    import time
    progress_file = ROOT / "data" / f"progress_{scenario_id}.json"
    try:
        current = {}
        if progress_file.exists():
            try:
                with open(progress_file, "r") as f:
                    current = json.load(f)
            except Exception:
                current = {}
        
        started_timestamp = current.get("started_timestamp")
        if not started_timestamp:
            started_timestamp = data.get("started_timestamp") or time.time()
            data["started_timestamp"] = started_timestamp

        now = time.time()
        if "elapsed_s" not in data:
            data["elapsed_s"] = round(now - started_timestamp, 1)

        current.update(data)
        with open(progress_file, "w") as pf:
            json.dump(current, pf)
    except Exception:
        pass


def _run_full_pipeline(run_id: int, engine: str, duration_s: int, seed: int, scenario_id: int):
    """Background task: run simulation + detection + proposals + persist."""
    import time
    from backend.database.db_connector import SessionLocal
    db = SessionLocal()
    t_start = time.time()
    started_at = datetime.now(timezone.utc).isoformat()

    _write_progress(scenario_id, {
        "scenario_id": scenario_id,
        "run_id": run_id,
        "status": "running",
        "progress": 2,
        "stage": "initializing",
        "stage_label": "Initializing simulation & loading network...",
        "started_at": started_at,
        "started_timestamp": t_start,
        "step": 0,
        "total_steps": duration_s,
        "elapsed_s": 0.0,
        "eta_s": None,
    })

    try:
        run = db.query(SimulationRun).get(run_id)
        if not run:
            return
        run.status = "running"
        db.commit()

        # ── Simulation ────────────────────────────────────────────────────────
        from simulation.simulation_runner import run_simulation
        try:
            telemetry = run_simulation(scenario_id=scenario_id, engine=engine, duration_s=duration_s, seed=seed)
        except RuntimeError as sumo_err:
            # SUMO binary not installed — mark run as failed and surface the message
            err_msg = str(sumo_err)
            log.error(f"Simulation engine error for run {run_id}: {err_msg}")
            run.status = "failed"
            run.agent_narrative = f"Engine error: {err_msg}"
            db.commit()
            _write_progress(scenario_id, {
                "progress": 0,
                "status": "failed",
                "stage": "failed",
                "stage_label": f"Engine error: {err_msg}",
                "error": err_msg,
                "elapsed_s": round(time.time() - t_start, 1),
                "eta_s": 0.0,
            })
            return

        # ── Metrics ───────────────────────────────────────────────────────────
        _write_progress(scenario_id, {
            "progress": 86,
            "stage": "metrics",
            "stage_label": "Calculating KPI metrics & congestion telemetry...",
            "elapsed_s": round(time.time() - t_start, 1),
            "eta_s": 4.0,
        })
        from validation.metrics_calculator import compute_metrics
        metrics = compute_metrics(telemetry)

        # ── Issue detection ───────────────────────────────────────────────────
        _write_progress(scenario_id, {
            "progress": 89,
            "stage": "issues",
            "stage_label": "Detecting congestion, safety & lane utilization issues...",
            "elapsed_s": round(time.time() - t_start, 1),
            "eta_s": 3.0,
        })
        from ai.issue_detection.congestion_detector import detect_congestion
        from ai.issue_detection.intersection_safety_analyzer import detect_unsafe_intersections
        from ai.issue_detection.lane_utilization_analyzer import detect_lane_issues

        all_issues = (
            detect_congestion(telemetry) +
            detect_unsafe_intersections(telemetry) +
            detect_lane_issues(telemetry)
        )

        # ── Fast DB Commit: Save baseline run telemetry ───────────────────────
        from backend.models.schema import Issue, Proposal

        run.status = "done"
        run.finished_at = datetime.now(timezone.utc)
        run.set_telemetry(telemetry)
        run.avg_travel_time_s = metrics.get("avg_travel_time_s")
        run.avg_wait_time_s   = metrics.get("avg_wait_time_s")
        run.avg_speed_kph     = metrics.get("avg_speed_kph")
        run.congestion_ratio  = metrics.get("congestion_ratio")
        run.total_delay_s     = metrics.get("total_delay_s")
        run.emissions_proxy   = metrics.get("emissions_proxy")
        run.efficiency_score  = metrics.get("efficiency_score")
        run.throughput_index  = metrics.get("throughput_index")
        if hasattr(run, "noise_pollution_db"):
            run.noise_pollution_db = metrics.get("noise_pollution_db")
        db.add(run)

        # Persist issues (cap at 200)
        for issue_data in all_issues[:200]:
            issue = Issue(
                run_id      = run_id,
                issue_id    = issue_data["issue_id"],
                type        = issue_data["type"],
                subtype     = issue_data.get("subtype"),
                severity    = issue_data["severity"],
                description = issue_data.get("description", ""),
                location_json = json.dumps(issue_data.get("location", {})),
                metrics_json  = json.dumps(issue_data.get("metrics", {})),
            )
            db.add(issue)

        db.commit()

        # ── Proposal generation & AI Agent analysis ───────────────────────────
        _write_progress(scenario_id, {
            "progress": 92,
            "stage": "proposals",
            "stage_label": "Generating AI signal timing, lane change & diversion proposals...",
            "elapsed_s": round(time.time() - t_start, 1),
            "eta_s": 2.5,
        })
        from ai.proposal_generator.signal_timing_optimizer import generate_signal_proposals
        from ai.proposal_generator.lane_change_recommender import generate_lane_proposals
        from ai.proposal_generator.route_diversion_planner import generate_diversion_proposals

        all_proposals = (
            generate_signal_proposals(all_issues, telemetry) +
            generate_lane_proposals(all_issues, telemetry) +
            generate_diversion_proposals(all_issues, telemetry)
        )

        # ── Zoning analysis (runs after main proposals; non-blocking) ─────────
        try:
            from ai.issue_detection.zoning_analyzer import detect_zoning_issues
            from ai.proposal_generator.zoning_proposer import generate_zoning_proposals
            zoning_issues    = detect_zoning_issues(telemetry, scenario_id=scenario_id)
            zoning_proposals = generate_zoning_proposals(zoning_issues)
            all_issues    = all_issues    + zoning_issues
            all_proposals = all_proposals + zoning_proposals
            log.info(
                f"Zoning pipeline: {len(zoning_issues)} issues, "
                f"{len(zoning_proposals)} proposals generated."
            )
        except Exception as ze:
            log.warning(f"Zoning analysis failed (non-critical): {ze}")

        _write_progress(scenario_id, {
            "progress": 96,
            "stage": "ai_agent",
            "stage_label": "City Inspector AI generating diagnostic narrative...",
            "elapsed_s": round(time.time() - t_start, 1),
            "eta_s": 1.0,
        })

        try:
            from ai.city_inspector_agent.llm_agent import CityInspectorAgent
            scenario = db.query(Scenario).get(scenario_id)
            agent = CityInspectorAgent()
            agent_result = agent.analyze(
                scenario_id=scenario_id,
                scenario_name=scenario.name if scenario else "Unknown",
                telemetry=telemetry,
                issues=all_issues,
            )
            if agent_result.get("narrative"):
                run.agent_narrative = agent_result.get("narrative")
                db.add(run)
        except Exception as e:
            log.warning(f"LLM agent failed (non-critical): {e}")

        # Persist proposals (cap at 50)
        for prop_data in all_proposals[:50]:
            proposal = Proposal(
                run_id      = run_id,
                proposal_id = prop_data["proposal_id"],
                type        = prop_data["type"],
                subtype     = prop_data.get("subtype"),
                description = prop_data.get("description", ""),
                parameters_json  = json.dumps(prop_data.get("parameters", {})),
                improvement_json = json.dumps(prop_data.get("expected_improvement", {})),
            )
            db.add(proposal)

        db.commit()

        # Mark 100% DONE with exact duration
        t_end = time.time()
        total_time_s = round(t_end - t_start, 1)
        _write_progress(scenario_id, {
            "progress": 100,
            "status": "done",
            "stage": "complete",
            "stage_label": "Simulation and AI optimization complete",
            "step": duration_s,
            "total_steps": duration_s,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "total_duration_s": total_time_s,
            "elapsed_s": total_time_s,
            "eta_s": 0.0,
        })
        log.info(f"Pipeline complete: run {run_id} in {total_time_s}s — {len(all_issues)} issues, {len(all_proposals)} proposals saved.")

    except Exception as e:
        log.error(f"Pipeline failed for run {run_id}: {e}", exc_info=True)
        run = db.query(SimulationRun).get(run_id)
        if run:
            run.status = "failed"
            db.commit()
        _write_progress(scenario_id, {
            "progress": 0,
            "status": "failed",
            "stage": "failed",
            "stage_label": f"Simulation failed: {e}",
            "error": str(e),
            "elapsed_s": round(time.time() - t_start, 1),
            "eta_s": 0.0,
        })
    finally:
        db.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/reset", tags=["System"])
def reset_system(db: Session = Depends(get_db)) -> dict:
    """Reset DB, delete all stale runs/proposals/validations, and clear caches."""
    from backend.database.db_connector import Base, engine, init_db
    try:
        db.close()
        Base.metadata.drop_all(bind=engine)
        init_db()

        # Delete progress files and report JSONs
        data_dir = ROOT / "data"
        for pf in data_dir.glob("progress_*.json"):
            try:
                pf.unlink()
            except Exception:
                pass

        reports_json_dir = ROOT / "data" / "processed" / "reports"
        if reports_json_dir.exists():
            for rf in reports_json_dir.glob("*.json"):
                try:
                    rf.unlink()
                except Exception:
                    pass

        log.info("System reset complete: DB tables re-created and stale telemetry cleared.")
        return {"status": "ok", "message": "Database and telemetry caches completely reset."}
    except Exception as e:
        log.error(f"Reset failed: {e}")
        raise HTTPException(500, f"Reset failed: {e}")


@router.post("", status_code=201)
def create_scenario(body: ScenarioCreate, db: Session = Depends(get_db)) -> dict:
    """Create a new scenario and trigger OSM data download."""
    # 1. Instantiate and commit the scenario to get a database ID first
    scenario = Scenario(
        name        = body.name,
        city        = body.city,
        description = body.description,
        n_nodes     = 0,
        n_edges     = 0,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    try:
        from simulation.osm_to_network import build_network
        meta = build_network(
            city=body.city,
            force_rebuild=body.force_rebuild,
            scenario_id=scenario.id
        )
    except Exception as err:
        log.error(f"Failed to build network for scenario '{body.name}' (ID {scenario.id}): {err}")
        # Clean up scenario if network download fails
        db.delete(scenario)
        db.commit()
        raise HTTPException(500, f"Network build failed: {err}")

    # 2. Populate scenario details from built network metadata
    scenario.bbox_north  = meta.get("bbox", {}).get("north")
    scenario.bbox_south  = meta.get("bbox", {}).get("south")
    scenario.bbox_east   = meta.get("bbox", {}).get("east")
    scenario.bbox_west   = meta.get("bbox", {}).get("west")
    scenario.n_nodes     = meta.get("nodes")
    scenario.n_edges     = meta.get("edges")
    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    log.info(f"Successfully created and built scenario {scenario.id}: {scenario.name} for city {scenario.city}")
    return {"scenario": scenario.to_dict(), "network_meta": meta}


@router.get("")
def list_scenarios(db: Session = Depends(get_db)) -> dict:
    scenarios = db.query(Scenario).order_by(Scenario.created_at.desc()).all()
    return {"scenarios": [s.to_dict() for s in scenarios]}


@router.get("/{scenario_id}")
def get_scenario(scenario_id: int, db: Session = Depends(get_db)) -> dict:
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")
    return {"scenario": scenario.to_dict()}


@router.delete("/{scenario_id}")
def delete_scenario(scenario_id: int, db: Session = Depends(get_db)) -> dict:
    """Delete scenario and all associated simulation runs, issues, proposals, and results."""
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")

    runs = db.query(SimulationRun).filter(SimulationRun.scenario_id == scenario_id).all()
    for r in runs:
        db.query(ValidationResult).filter(ValidationResult.scenario_id == scenario_id).delete()
        db.query(Proposal).filter(Proposal.run_id == r.id).delete()
        db.query(Issue).filter(Issue.run_id == r.id).delete()
        db.delete(r)

    db.delete(scenario)
    db.commit()

    # Clear progress file
    pf = ROOT / "data" / f"progress_{scenario_id}.json"
    if pf.exists():
        try:
            pf.unlink()
        except Exception:
            pass

    log.info(f"Deleted scenario {scenario_id} and all associated records.")
    return {"status": "ok", "message": f"Scenario {scenario_id} deleted successfully."}


@router.post("/{scenario_id}/simulate", status_code=202)
def simulate(
    scenario_id: int,
    body: SimulateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    """Start a baseline simulation run for the scenario (async)."""
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")

    run = SimulationRun(
        scenario_id = scenario_id,
        engine      = body.engine,
        duration_s  = body.duration_s,
        seed        = body.seed,
        status      = "pending",
        is_baseline = True,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    background_tasks.add_task(
        _run_full_pipeline,
        run_id=run.id, engine=body.engine,
        duration_s=body.duration_s, seed=body.seed,
        scenario_id=scenario_id,
    )
    log.info(f"Simulation run {run.id} queued for scenario {scenario_id}.")
    return {"run": run.to_dict(), "message": "Simulation started in background."}


@router.get("/{scenario_id}/runs")
def list_runs(scenario_id: int, db: Session = Depends(get_db)) -> dict:
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")
    runs = db.query(SimulationRun).filter(SimulationRun.scenario_id == scenario_id).all()
    return {"runs": [r.to_dict() for r in runs]}


class SignalOverride(BaseModel):
    node_id: int
    green_s: int = Field(default=30, ge=10, le=120)
    amber_s: int = Field(default=3, ge=2, le=5)
    red_s: int = Field(default=30, ge=10, le=120)
    is_signal: bool = Field(default=True, description="Whether this node should be a traffic signal")
    lanes: int | None = Field(default=None, ge=1, le=4, description="Lanes count for streets connected to this node")
    has_sidewalk: bool | None = Field(default=None, description="Whether connected streets should have a sidewalk")
    has_dustbin: bool | None = Field(default=None, description="Whether this node has dustbins")


class CustomConfigValidationRequest(BaseModel):
    overrides: list[SignalOverride]


@router.post("/{scenario_id}/test-custom-config")
def test_custom_config(
    scenario_id: int,
    body: CustomConfigValidationRequest,
    db: Session = Depends(get_db)
) -> dict:
    """
    Runs a custom simulation with user-defined signal timings.
    Does not modify database records. Simulates and returns comparison deltas.
    """
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")

    # Get baseline telemetry from latest done run
    from backend.api.routes_dashboard import _latest_done_run
    baseline_run = _latest_done_run(scenario_id, db)
    if not baseline_run:
        raise HTTPException(400, "Please run a baseline simulation first.")

    # Translate overrides to applied proposals format
    apply_proposals = []
    for override in body.overrides:
        if not override.is_signal:
            continue
        # Webster split comparison simulation
        import math
        opt_green = 35.0  # reference green split
        diff = abs(override.green_s - opt_green) / opt_green
        reduction = 35.0 * math.exp(-3.0 * diff)

        apply_proposals.append({
            "type": "signal_timing",
            "location": {
                "node_id": override.node_id
            },
            "green_s": float(override.green_s),
            "yellow_s": float(override.amber_s),
            "expected_improvement": {
                "expected_wait_reduction_pct": float(reduction)
            }
        })

    # Load graph and apply junction type changes (install/remove signals, lanes, footpaths, dustbins)
    from simulation.simulation_runner import load_graph, run_simulation
    G = load_graph(scenario_id)
    G_modified = G.copy()
    for override in body.overrides:
        nid = override.node_id
        found_key = None
        if str(nid) in G_modified.nodes:
            found_key = str(nid)
        elif int(nid) in G_modified.nodes:
            found_key = int(nid)
            
        if found_key is not None:
            # 1. Traffic signal toggle
            if override.is_signal:
                G_modified.nodes[found_key]["highway"] = "traffic_signals"
            else:
                G_modified.nodes[found_key]["highway"] = "priority"
                
            # 2. Lanes (road width)
            if override.lanes is not None:
                for u, v, k, data in list(G_modified.edges(data=True, keys=True)):
                    if u == found_key or v == found_key:
                        G_modified[u][v][k]["lanes"] = override.lanes
                        G_modified[u][v][k]["capacity"] = override.lanes * 900
                        
            # 3. Footpaths (sidewalks)
            if override.has_sidewalk is not None:
                width = 2.0 if override.has_sidewalk else 0.0
                for u, v, k, data in list(G_modified.edges(data=True, keys=True)):
                    if u == found_key or v == found_key:
                        G_modified[u][v][k]["sidewalk_width"] = width
                        
            # 4. Dustbins (POI overlay annotation layer)
            if override.has_dustbin is not None:
                G_modified.nodes[found_key]["has_dustbin"] = override.has_dustbin

    # Run the custom simulation
    import time
    t_custom_start = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    _write_progress(scenario_id, {
        "scenario_id": scenario_id,
        "status": "running",
        "progress": 2,
        "stage": "initializing",
        "stage_label": "Preparing sandbox network & signal overrides...",
        "started_at": started_at,
        "started_timestamp": t_custom_start,
        "step": 0,
        "total_steps": baseline_run.duration_s,
        "elapsed_s": 0.0,
        "eta_s": None,
    })

    try:
        custom_telemetry = run_simulation(
            scenario_id=scenario_id,
            engine=baseline_run.engine,
            duration_s=baseline_run.duration_s,
            seed=baseline_run.seed,
            apply_proposals=apply_proposals,
            G=G_modified
        )

        # Compute custom metrics
        _write_progress(scenario_id, {
            "progress": 90,
            "stage": "metrics",
            "stage_label": "Calculating sandbox KPI deltas & comparison...",
            "elapsed_s": round(time.time() - t_custom_start, 1),
            "eta_s": 1.0,
        })
        from validation.metrics_calculator import compute_metrics
        custom_metrics = compute_metrics(custom_telemetry)

        baseline_metrics = {
            "avg_travel_time_s": baseline_run.avg_travel_time_s,
            "avg_wait_time_s":   baseline_run.avg_wait_time_s,
            "avg_speed_kph":     baseline_run.avg_speed_kph,
            "congestion_ratio":  baseline_run.congestion_ratio,
            "total_delay_s":     baseline_run.total_delay_s,
            "emissions_proxy":   baseline_run.emissions_proxy,
            "efficiency_score":  baseline_run.efficiency_score,
            "noise_pollution_db": getattr(baseline_run, "noise_pollution_db", 0.0) or 0.0,
        }

        # Generate comparative deltas
        deltas = {}
        for k, val in custom_metrics.items():
            if k in baseline_metrics and val is not None and baseline_metrics[k] is not None:
                base_val = baseline_metrics[k]
                diff_val = val - base_val
                pct_val = (diff_val / max(base_val, 1) * 100) if base_val != 0 else 0
                deltas[k] = {
                    "before": round(base_val, 2),
                    "after":  round(val, 2),
                    "diff":   round(diff_val, 2),
                    "pct":    round(pct_val, 1)
                }

        t_custom_end = time.time()
        total_time_s = round(t_custom_end - t_custom_start, 1)
        _write_progress(scenario_id, {
            "progress": 100,
            "status": "done",
            "stage": "complete",
            "stage_label": "Sandbox test complete",
            "total_duration_s": total_time_s,
            "elapsed_s": total_time_s,
            "eta_s": 0.0,
        })

        return {
            "scenario_id": scenario_id,
            "metrics":     custom_metrics,
            "deltas":      deltas,
            "telemetry":   custom_telemetry
        }
    except Exception as e:
        _write_progress(scenario_id, {
            "progress": 0,
            "status": "failed",
            "stage": "failed",
            "stage_label": f"Sandbox test failed: {e}",
            "error": str(e),
            "elapsed_s": round(time.time() - t_custom_start, 1),
            "eta_s": 0.0,
        })
        raise


@router.get("/{scenario_id}/nodes/{node_id}/optimize")
def optimize_node_signal(
    scenario_id: int,
    node_id: int,
    db: Session = Depends(get_db)
) -> dict:
    """
    AI-powered Webster's Equation signal optimization for a given junction.

    Returns optimally computed green_s, amber_s, red_s splits based on
    approach lane capacities and simulated flow from the last baseline run.

    Webster's Method:
      Y = sum(flow_i / capacity_i)  for each critical lane i
      C0 = (1.5 * L + 5) / (1 - Y)  optimal cycle length
      Green_i = (C0 - L) * (y_i / Y)  per-approach green split
    """
    import math
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")

    from backend.api.routes_dashboard import _latest_done_run
    baseline_run = _latest_done_run(scenario_id, db)
    if not baseline_run:
        raise HTTPException(400, "No baseline simulation found. Run a simulation first.")

    from simulation.simulation_runner import load_graph
    G = load_graph(scenario_id)

    if node_id not in G.nodes:
        raise HTTPException(404, f"Node {node_id} not found in network graph.")

    # Collect incoming edge approaches
    incoming_edges = []
    for u, v, k, data in G.edges(data=True, keys=True):
        if v == node_id:
            lanes = data.get("lanes", 1)
            if isinstance(lanes, list):
                lanes = int(lanes[0])
            else:
                lanes = int(lanes) if lanes else 1
            speed_kph = float(data.get("speed_kph", 40))
            capacity = lanes * 900  # veh/hr per standard lane
            # Estimate flow from baseline telemetry
            telemetry = baseline_run.get_telemetry()
            edge_id = f"{u}_{v}_{k}"
            edge_data = next((e for e in telemetry.get("edges", []) if e.get("edge_id") == edge_id), None)
            flow = edge_data["flow"] if edge_data else (capacity * 0.4)
            incoming_edges.append({
                "edge_id": edge_id,
                "lanes": lanes,
                "capacity": capacity,
                "flow": flow,
                "y": flow / max(capacity, 1)
            })

    if not incoming_edges:
        # Node exists but has no incoming edges (source node) — return defaults
        return {"green_s": 30, "amber_s": 3, "red_s": 30, "cycle_s": 63, "method": "default"}

    # Webster's Equation
    n_approaches = len(incoming_edges)
    L = max(2, n_approaches)  # total lost time per cycle (sec)
    Y = sum(e["y"] for e in incoming_edges)
    Y = min(Y, 0.85)  # cap Y to avoid division explosion

    C0 = (1.5 * L + 5) / max(1 - Y, 0.01)
    C0 = max(30, min(int(round(C0)), 180))  # clamp 30–180s

    effective_green = C0 - L

    # Allocate green proportionally among approaches
    # Critical approach = highest y_i
    dominant_y = max(e["y"] for e in incoming_edges)
    dominant_y = max(dominant_y, 0.01)

    # For a simple 2-phase controller (most Davanagere intersections)
    # Allocate main approach green = effective_green * dominant_y / Y
    main_green = int(round(effective_green * dominant_y / max(Y, 0.01)))
    main_green = max(10, min(main_green, 120))
    amber = 3
    red = max(10, C0 - main_green - amber)
    red = min(red, 120)

    return {
        "green_s": main_green,
        "amber_s": amber,
        "red_s":   red,
        "cycle_s": C0,
        "Y":       round(Y, 4),
        "approaches": len(incoming_edges),
        "method": "webster"
    }


@router.post("/{scenario_id}/nodes/{node_id}/ai-redesign")
def ai_redesign(scenario_id: int, node_id: int, db: Session = Depends(get_db)) -> dict:
    """
    AI Agent redesigns the intersection (signals, road width, footpaths, dustbins)
    applying optimal rules and Webster calculations.
    """
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")

    from backend.api.routes_dashboard import _latest_done_run
    baseline_run = _latest_done_run(scenario_id, db)
    if not baseline_run:
        raise HTTPException(400, "No baseline simulation found. Run a simulation first.")

    from simulation.simulation_runner import load_graph
    G = load_graph(scenario_id)

    found_key = None
    if str(node_id) in G.nodes:
        found_key = str(node_id)
    elif int(node_id) in G.nodes:
        found_key = int(node_id)

    if found_key is None:
        raise HTTPException(404, f"Node {node_id} not found in network graph.")

    # 1. Analyze approaches
    incoming_edges = []
    total_flow = 0.0
    for u, v, k, data in G.edges(data=True, keys=True):
        if v == found_key:
            lanes = data.get("lanes", 1)
            if isinstance(lanes, list):
                lanes = int(lanes[0])
            else:
                lanes = int(lanes) if lanes else 1
            capacity = lanes * 900
            
            telemetry = baseline_run.get_telemetry()
            edge_id = f"{u}_{v}_{k}"
            edge_data = next((e for e in telemetry.get("edges", []) if e.get("edge_id") == edge_id), None)
            flow = edge_data["flow"] if edge_data else (capacity * 0.4)
            total_flow += flow
            incoming_edges.append({
                "flow": flow,
                "capacity": capacity,
                "y": flow / max(capacity, 1)
            })

    # 2. Decision making rules
    street_count = len(incoming_edges)
    is_signal = street_count >= 4 or total_flow > 1200
    
    # Lanes redesign (Road width)
    if total_flow > 1500 or any(e["y"] > 0.75 for e in incoming_edges):
        lanes_recommend = 3
        lanes_reason = "Widened approaches to 3 lanes to handle severe congestion and bottleneck queues"
    elif total_flow > 800:
        lanes_recommend = 2
        lanes_reason = "Optimized to 2 lanes to accommodate moderate vehicle traffic flow"
    else:
        lanes_recommend = 1
        lanes_reason = "Maintained single-lane configuration appropriate for lower traffic density"

    # Footpath (Sidewalk) redesign
    has_sidewalk = street_count >= 3
    sidewalk_reason = "Added 2m pedestrian footpaths to ensure safety at this multi-way junction" if has_sidewalk else "Sidewalks not required for low-conflict two-way link"

    # Dustbin redesign
    has_dustbin = has_sidewalk and street_count >= 4
    dustbin_reason = "Placed waste disposal bins at high-occupancy crossing zones" if has_dustbin else "Litter density does not warrant dedicated waste bins here"

    # Signals timing redesign via Webster
    green_s = 30
    amber_s = 3
    red_s = 30
    cycle_s = 60
    signal_reason = "Installed active signal control to regulate high-conflict vehicle paths"
    
    if is_signal and incoming_edges:
        L = max(2, street_count)
        Y = sum(e["y"] for e in incoming_edges)
        Y = min(Y, 0.85)
        C0 = (1.5 * L + 5) / max(1 - Y, 0.01)
        C0 = max(30, min(int(round(C0)), 120))
        effective_green = C0 - L
        dominant_y = max(e["y"] for e in incoming_edges)
        dominant_y = max(dominant_y, 0.01)
        
        green_s = int(round(effective_green * dominant_y / max(Y, 0.01)))
        green_s = max(10, min(green_s, 90))
        red_s = max(10, C0 - green_s - amber_s)
        cycle_s = C0
        signal_reason = f"Optimized green phase to {green_s}s (Cycle: {C0}s) using Webster's flow equation"
    elif not is_signal:
        signal_reason = "Reverted to priority rules (unsignalized) to eliminate unnecessary idling delay"

    reasoning_list = [lanes_reason, sidewalk_reason, dustbin_reason, signal_reason]
    full_reasoning = " · ".join(reasoning_list)

    return {
        "node_id": node_id,
        "is_signal": is_signal,
        "green_s": green_s,
        "amber_s": amber_s,
        "red_s": red_s,
        "lanes": lanes_recommend,
        "has_sidewalk": has_sidewalk,
        "has_dustbin": has_dustbin,
        "reasoning": full_reasoning
    }


@router.get("/{scenario_id}/progress")
def get_scenario_progress(scenario_id: int) -> dict:
    """Check live simulation run progress for this scenario."""
    from pathlib import Path
    import json
    import time
    ROOT = Path(__file__).resolve().parent.parent.parent
    progress_file = ROOT / "data" / f"progress_{scenario_id}.json"
    
    if progress_file.exists():
        try:
            with open(progress_file, "r") as f:
                data = json.load(f)
                if data.get("status") == "running" and data.get("started_timestamp"):
                    data["elapsed_s"] = round(time.time() - float(data["started_timestamp"]), 1)
                return data
        except Exception:
            pass
    return {"progress": 0, "status": "idle"}


# ── Phase 15 APIs ─────────────────────────────────────────────────────────────

scenario_router = APIRouter(prefix="/scenario", tags=["Scenario (Phase 15)"])


@scenario_router.post("")
def create_scenario_alt(body: ScenarioCreate, db: Session = Depends(get_db)) -> dict:
    """Create a new simulation scenario from a map area (Phase 15)."""
    return create_scenario(body=body, db=db)


@scenario_router.post("/{scenario_id}/run")
def run_simulation_alt(
    scenario_id: int,
    body: SimulateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> dict:
    """Run baseline simulation for a scenario (Phase 15)."""
    return simulate(scenario_id=scenario_id, body=body, background_tasks=background_tasks, db=db)


@scenario_router.post("/{scenario_id}/modify")
def modify_scenario_alt(
    scenario_id: int,
    body: CustomConfigValidationRequest,
    db: Session = Depends(get_db)
) -> dict:
    """Apply signal/lane custom modifications to a scenario (Phase 15)."""
    return test_custom_config(scenario_id=scenario_id, body=body, db=db)


@scenario_router.get("/{scenario_id}/recommendations")
def get_recommendations_alt(
    scenario_id: int,
    proposal_type: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db)
) -> dict:
    """Retrieve AI-generated optimization recommendations/proposals (Phase 15)."""
    from backend.api.routes_ai import get_proposals
    return get_proposals(scenario_id=scenario_id, proposal_type=proposal_type, limit=limit, db=db)


# ── Municipal Planning: Signal Capacity & N-Vehicle What-If Analyzer ──────────

class CapacityAnalysisRequest(BaseModel):
    flow: float = Field(default=500, ge=0, le=5000, description="Arriving vehicle flow (veh/h)")
    green_s: int = Field(default=35, ge=5, le=120, description="Green phase duration (s)")
    amber_s: int = Field(default=3, ge=2, le=10, description="Amber/clearance phase (s)")
    red_s: int   = Field(default=35, ge=5, le=120, description="Red phase duration (s)")
    lanes: int   = Field(default=1, ge=1, le=6, description="Number of approach lanes")
    phf: float   = Field(default=0.92, ge=0.7, le=1.0, description="Peak Hour Factor (IRC default 0.92)")


@router.post("/{scenario_id}/nodes/{node_id}/capacity-analysis")
def analyze_signal_capacity(
    scenario_id: int,
    node_id: int,
    body: CapacityAnalysisRequest,
    db: Session = Depends(get_db)
) -> dict:
    """
    Signal Capacity & N-Vehicle What-If Outcome Analyzer.

    Computes IRC:106-2010 / HCM-based real-world signal capacity, saturation,
    Webster's control delay, queue backlog (vehicles & meters), Level of Service
    (LOS Grade A-F), and actionable municipal engineering recommendations.
    """
    try:
        from ai.proposal_generator.capacity_analyzer import analyze_capacity
        result = analyze_capacity(
            flow=body.flow,
            green_s=body.green_s,
            amber_s=body.amber_s,
            red_s=body.red_s,
            lanes=body.lanes,
            phf=body.phf,
        )
        return {"scenario_id": scenario_id, "node_id": node_id, "analysis": result}
    except Exception as e:
        log.error(f"Capacity analysis failed for node {node_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── Municipal Planning: Road Service / Maintenance Detour Route Planner ───────

class ServiceDetourRequest(BaseModel):
    closure_type: str  = Field(default="full", description="full | partial | junction")
    duration_days: int = Field(default=7, ge=1, le=365, description="Estimated closure duration in days")
    source_node: int | None = Field(default=None, description="Override source node for routing")
    target_node: int | None = Field(default=None, description="Override target node for routing")


@router.post("/{scenario_id}/nodes/{node_id}/service-detour")
def plan_road_service_detour(
    scenario_id: int,
    node_id: int,
    body: ServiceDetourRequest,
    db: Session = Depends(get_db)
) -> dict:
    """
    Road Maintenance & Service Closure — Citizen Detour Route Planner.

    When a junction or road segment is closed for maintenance:
      - Computes top-2 alternative citizen detour routes via the OSM road graph.
      - Returns GeoJSON coordinates for interactive map rendering.
      - Quantifies citizen delay impact (extra minutes, extra km).
      - Identifies spillover traffic on secondary residential streets.
      - Generates an official Municipal Management & Traffic Police Action Plan.
    """
    try:
        from ai.proposal_generator.service_detour_planner import plan_service_detour
        result = plan_service_detour(
            node_id=node_id,
            closure_type=body.closure_type,
            duration_days=body.duration_days,
            source_node=body.source_node,
            target_node=body.target_node,
        )
        return {"scenario_id": scenario_id, "node_id": node_id, "detour": result}
    except Exception as e:
        log.error(f"Service detour planning failed for node {node_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



@scenario_router.post("")
def create_scenario_alt(body: ScenarioCreate, db: Session = Depends(get_db)) -> dict:
    """Create a new simulation scenario from a map area (Phase 15)."""
    return create_scenario(body=body, db=db)


@scenario_router.post("/{scenario_id}/run")
def run_simulation_alt(
    scenario_id: int,
    body: SimulateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> dict:
    """Run baseline simulation for a scenario (Phase 15)."""
    return simulate(scenario_id=scenario_id, body=body, background_tasks=background_tasks, db=db)


@scenario_router.post("/{scenario_id}/modify")
def modify_scenario_alt(
    scenario_id: int,
    body: CustomConfigValidationRequest,
    db: Session = Depends(get_db)
) -> dict:
    """Apply signal/lane custom modifications to a scenario (Phase 15)."""
    return test_custom_config(scenario_id=scenario_id, body=body, db=db)


@scenario_router.get("/{scenario_id}/recommendations")
def get_recommendations_alt(
    scenario_id: int,
    proposal_type: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db)
) -> dict:
    """Retrieve AI-generated optimization recommendations/proposals (Phase 15)."""
    from backend.api.routes_ai import get_proposals
    return get_proposals(scenario_id=scenario_id, proposal_type=proposal_type, limit=limit, db=db)

