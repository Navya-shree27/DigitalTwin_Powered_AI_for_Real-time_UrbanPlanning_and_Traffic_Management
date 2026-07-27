"""
backend/api/routes_dashboard.py
─────────────────────────────────
Aggregated dashboard endpoints.

Endpoints
─────────
  GET /api/scenarios/{scenario_id}/metrics   — baseline KPIs for chart rendering
  GET /api/dashboard/{scenario_id}            — single aggregated payload for dashboard
  GET /api/dashboard/{scenario_id}/geojson   — network GeoJSON for map rendering
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database.db_connector import get_db
from backend.models.schema import Issue, Proposal, Scenario, SimulationRun, ValidationResult

log = logging.getLogger("routes_dashboard")
router = APIRouter(tags=["Dashboard"])

ROOT = Path(__file__).resolve().parent.parent.parent
NETWORK_GEOJSON = ROOT / "data" / "processed" / "network" / "network.geojson"
NODES_GEOJSON   = ROOT / "data" / "processed" / "network" / "nodes.geojson"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_done_run(scenario_id: int, db: Session) -> SimulationRun | None:
    return (
        db.query(SimulationRun)
        .filter(SimulationRun.scenario_id == scenario_id, SimulationRun.status == "done")
        .order_by(SimulationRun.finished_at.desc())
        .first()
    )


def _run_metrics(run: SimulationRun) -> dict:
    return {
        "avg_travel_time_s": run.avg_travel_time_s,
        "avg_wait_time_s":   run.avg_wait_time_s,
        "avg_speed_kph":     run.avg_speed_kph,
        "congestion_ratio":  run.congestion_ratio,
        "total_delay_s":     run.total_delay_s,
        "emissions_proxy":   run.emissions_proxy,
        "efficiency_score":  run.efficiency_score,
        "throughput_index":  run.throughput_index,
        "noise_pollution_db": getattr(run, "noise_pollution_db", 0.0) or 0.0,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/scenarios/{scenario_id}/metrics")
def get_metrics(scenario_id: int, db: Session = Depends(get_db)) -> dict:
    run = _latest_done_run(scenario_id, db)
    if not run:
        raise HTTPException(404, f"No completed run for scenario {scenario_id}.")

    return {
        "scenario_id": scenario_id,
        "run_id":      run.id,
        "engine":      run.engine,
        "duration_s":  run.duration_s,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "metrics":     _run_metrics(run),
    }


@router.get("/api/dashboard/{scenario_id}")
def get_dashboard(scenario_id: int, db: Session = Depends(get_db)) -> dict:
    """
    Single aggregated payload for the frontend dashboard.
    Includes: scenario info, metrics, issue summary, top proposals.
    """
    scenario = db.query(Scenario).get(scenario_id)
    if not scenario:
        raise HTTPException(404, f"Scenario {scenario_id} not found.")

    # Get the latest run (could be running, pending, done, or failed)
    run = (
        db.query(SimulationRun)
        .filter(SimulationRun.scenario_id == scenario_id)
        .order_by(SimulationRun.created_at.desc())
        .first()
    )

    if run is None:
        # Scenario exists but no simulation run yet
        return {
            "scenario":     scenario.to_dict(),
            "run":          None,
            "metrics":      None,
            "issue_summary": {"total": 0, "severe": 0, "moderate": 0, "low": 0},
            "top_issues":   [],
            "top_proposals": [],
            "validated_proposals": [],
            "status":       "no_run",
        }

    # If the latest run is in progress, return its status so the frontend loader spins,
    # but try to load the previous completed run's data so the dashboard doesn't look empty
    if run.status in ["running", "pending"]:
        latest_done = (
            db.query(SimulationRun)
            .filter(SimulationRun.scenario_id == scenario_id, SimulationRun.status == "done")
            .order_by(SimulationRun.finished_at.desc())
            .first()
        )
        if latest_done:
            all_issues = db.query(Issue).filter(Issue.run_id == latest_done.id).all()
            priority   = {"severe": 0, "moderate": 1, "low": 2}
            top_issues = sorted(all_issues, key=lambda i: priority.get(i.severity, 3))[:10]
            issue_summary = {
                "total":    len(all_issues),
                "severe":   sum(1 for i in all_issues if i.severity == "severe"),
                "moderate": sum(1 for i in all_issues if i.severity == "moderate"),
                "low":      sum(1 for i in all_issues if i.severity == "low"),
            }
            all_proposals = db.query(Proposal).filter(Proposal.run_id == latest_done.id).all()
            top_proposals = all_proposals[:10]
            
            validated_proposals = []
            for p in all_proposals:
                if p.validated:
                    vr = db.query(ValidationResult).filter(
                        ValidationResult.proposal_id_fk == p.id
                    ).first()
                    validated_proposals.append({
                        "proposal":   p.to_dict(),
                        "validation": vr.to_dict() if vr else None,
                    })

            return {
                "scenario":     scenario.to_dict(),
                "run":          run.to_dict(),
                "metrics":      _run_metrics(latest_done),
                "issue_summary": issue_summary,
                "top_issues":   [i.to_dict() for i in top_issues],
                "top_proposals": [p.to_dict() for p in top_proposals],
                "validated_proposals": validated_proposals,
                "status":       "running",
            }
        else:
            return {
                "scenario":     scenario.to_dict(),
                "run":          run.to_dict(),
                "metrics":      None,
                "issue_summary": {"total": 0, "severe": 0, "moderate": 0, "low": 0},
                "top_issues":   [],
                "top_proposals": [],
                "validated_proposals": [],
                "status":       "running",
            }

    # If the latest run failed
    if run.status == "failed":
        return {
            "scenario":     scenario.to_dict(),
            "run":          run.to_dict(),
            "metrics":      None,
            "issue_summary": {"total": 0, "severe": 0, "moderate": 0, "low": 0},
            "top_issues":   [],
            "top_proposals": [],
            "validated_proposals": [],
            "status":       "failed",
        }

    # Default: latest run is done and loaded
    all_issues = db.query(Issue).filter(Issue.run_id == run.id).all()
    priority   = {"severe": 0, "moderate": 1, "low": 2}
    top_issues = sorted(all_issues, key=lambda i: priority.get(i.severity, 3))[:10]

    issue_summary = {
        "total":    len(all_issues),
        "severe":   sum(1 for i in all_issues if i.severity == "severe"),
        "moderate": sum(1 for i in all_issues if i.severity == "moderate"),
        "low":      sum(1 for i in all_issues if i.severity == "low"),
    }

    all_proposals = db.query(Proposal).filter(Proposal.run_id == run.id).all()
    top_proposals = all_proposals[:10]

    validated_proposals = []
    for p in all_proposals:
        if p.validated:
            vr = db.query(ValidationResult).filter(
                ValidationResult.proposal_id_fk == p.id
            ).first()
            validated_proposals.append({
                "proposal":   p.to_dict(),
                "validation": vr.to_dict() if vr else None,
            })

    return {
        "scenario":     scenario.to_dict(),
        "run":          run.to_dict(),
        "metrics":      _run_metrics(run),
        "issue_summary": issue_summary,
        "top_issues":   [i.to_dict() for i in top_issues],
        "top_proposals": [p.to_dict() for p in top_proposals],
        "validated_proposals": validated_proposals,
        "status":       "ready",
    }


@router.get("/api/dashboard/{scenario_id}/geojson/network")
def get_network_geojson(scenario_id: int) -> FileResponse:
    """Serve the road network GeoJSON for map rendering."""
    if not NETWORK_GEOJSON.exists():
        raise HTTPException(404, "Network GeoJSON not yet generated. Run a scenario first.")
    return FileResponse(
        str(NETWORK_GEOJSON),
        media_type="application/geo+json",
        filename="network.geojson",
    )


@router.get("/api/dashboard/{scenario_id}/geojson/nodes")
def get_nodes_geojson(scenario_id: int) -> FileResponse:
    """Serve node (intersection) GeoJSON for marker rendering.
    Forces synchronization of nodes.geojson with target real-world signals in node_mapping.json.
    """
    try:
        mapping_path = ROOT / "data" / "node_mapping.json"
        if mapping_path.exists() and NODES_GEOJSON.exists():
            with open(mapping_path, "r", encoding="utf-8") as f_map:
                mapped_junctions = json.load(f_map)
            
            mapped_signals = {str(item["osmid"]): item["name"] for item in mapped_junctions}
            
            with open(NODES_GEOJSON, "r", encoding="utf-8") as f_nodes:
                nodes_data = json.load(f_nodes)
                
            features = nodes_data.get("features", [])
            modified = False
            for feat in features:
                props = feat.get("properties", {})
                osmid_str = str(props.get("osmid", ""))
                if osmid_str in mapped_signals:
                    if props.get("highway") != "traffic_signals" or props.get("designation") != mapped_signals[osmid_str]:
                        props["highway"] = "traffic_signals"
                        props["designation"] = mapped_signals[osmid_str]
                        modified = True
            
            if modified:
                with open(NODES_GEOJSON, "w", encoding="utf-8") as f_write:
                    json.dump(nodes_data, f_write, indent=2)
                log.info("Successfully synchronized nodes.geojson with real-world traffic signals.")
    except Exception as e:
        log.error(f"Failed to synchronize traffic signals in nodes.geojson: {e}")

    return FileResponse(
        str(NODES_GEOJSON),
        media_type="application/geo+json",
        filename="nodes.geojson",
    )


@router.get("/api/dashboard/{scenario_id}/telemetry")
def get_telemetry(scenario_id: int, db: Session = Depends(get_db)) -> dict:
    """Get the telemetry of the latest completed run of the scenario."""
    run = _latest_done_run(scenario_id, db)
    if not run:
        raise HTTPException(404, f"No completed run for scenario {scenario_id}.")
    return run.get_telemetry()

