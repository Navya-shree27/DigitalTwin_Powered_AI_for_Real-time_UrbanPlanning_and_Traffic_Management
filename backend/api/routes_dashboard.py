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
    Dynamically rebuilds nodes.geojson with OSM tags if stale/lacking attributes.
    """
    needs_regen = True
    if NODES_GEOJSON.exists():
        try:
            with open(NODES_GEOJSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                features = data.get("features", [])
                for feat in features[:150]:  # check first 150 features
                    if feat.get("properties", {}).get("highway") == "traffic_signals":
                        needs_regen = False
                        break
        except Exception as e:
            log.warning(f"Error checking nodes.geojson: {e}")
            needs_regen = True

    # Always do the nearest-node mapping mapping for the 10 real-world junctions on load if regen is needed
    graphml_path = ROOT / "data" / "processed" / "network" / "network.graphml"
    if graphml_path.exists() and needs_regen:
        try:
            import osmnx as ox
            import pandas as pd
            
            log.info("Loading network graphml to resolve real-world signal coordinates...")
            G = ox.load_graphml(str(graphml_path))
            gdf_nodes = ox.graph_to_gdfs(G, nodes=True, edges=False).reset_index()
            
            # Debug: Check which of our target junctions are actually in the graphml
            target_ids = [571395243, 571407773, 1470841066, 1465243476, 1822610272, 1782305061, 2702258541, 1782236061, 1464736528, 1782269831]
            graphml_ids = gdf_nodes["osmid"].astype(str).tolist()
            present_in_graph = [tid for tid in target_ids if str(tid) in graphml_ids]
            
            # Also find all OSM IDs in the first 20 nodes of nodes.geojson that are close to lat 14.46
            close_nodes = gdf_nodes[gdf_nodes["y"].between(14.45, 14.48)]
            
            raise HTTPException(400, {
                "total_nodes_in_graph": len(gdf_nodes),
                "target_ids_sought": target_ids,
                "present_in_graph": present_in_graph,
                "nodes_near_davangere_center_count": len(close_nodes),
                "sample_near_nodes": close_nodes[["osmid", "y", "x"]].head(10).to_dict(orient="records")
            })
            
            target_junctions = [
                {"name": "Aruna Theatre Junction", "lat": 14.4678344, "lon": 75.9145766},
                {"name": "Vidyarthi Bhavan Junction", "lat": 14.4592308, "lon": 75.9198481},
                {"name": "Mothi Circle (PB Road)", "lat": 14.4644, "lon": 75.9175},
                {"name": "Gandhi Circle", "lat": 14.4657, "lon": 75.9227},
                {"name": "District Court Junction", "lat": 14.4618, "lon": 75.9196},
                {"name": "8th Main / PB Road Signal", "lat": 14.4634, "lon": 75.9157},
                {"name": "KSRTC Bus Stand Junction", "lat": 14.4668, "lon": 75.9157},
                {"name": "Vinobanagar Circle", "lat": 14.4560, "lon": 75.9155},
                {"name": "SBI / Collector Office", "lat": 14.4640, "lon": 75.9195},
                {"name": "Anjaneya Temple Road", "lat": 14.4605, "lon": 75.9220},
            ]
            
            matched_nodes = []
            for j in target_junctions:
                node_id = ox.nearest_nodes(G, X=j["lon"], Y=j["lat"])
                node_data = G.nodes[node_id]
                matched_nodes.append({
                    "name": j["name"],
                    "osmid": int(node_id),
                    "lat": float(node_data["y"]),
                    "lon": float(node_data["x"]),
                    "street_count": int(node_data.get("street_count", 3))
                })
                
            mapping_path = ROOT / "data" / "node_mapping.json"
            with open(mapping_path, "w", encoding="utf-8") as f_map:
                json.dump(matched_nodes, f_map, indent=2)
            log.info(f"Successfully wrote exact node coordinates to {mapping_path}")
            
            # Now update the nodes.geojson with these traffic signals!
            gdf_nodes = ox.graph_to_gdfs(G, nodes=True, edges=False).reset_index()
            
            # Add highway column if missing
            if "highway" not in gdf_nodes.columns:
                gdf_nodes["highway"] = None
                
            # Set target nodes as traffic_signals (using string comparison because graphml IDs are loaded as strings/objects)
            matched_ids_str = [str(m["osmid"]) for m in matched_nodes]
            gdf_nodes["osmid_str"] = gdf_nodes["osmid"].astype(str)
            gdf_nodes.loc[gdf_nodes["osmid_str"].isin(matched_ids_str), "highway"] = "traffic_signals"
            
            # Map designation names for UI display
            gdf_nodes["designation"] = None
            for m in matched_nodes:
                gdf_nodes.loc[gdf_nodes["osmid_str"] == str(m["osmid"]), "designation"] = m["name"]
            
            cols = ["osmid", "geometry", "street_count"]
            for col_name in ("highway", "designation", "name", "ref"):
                if col_name in gdf_nodes.columns:
                    cols.append(col_name)
                    
            gdf_nodes = gdf_nodes[cols]
            
            # Stringify list-valued columns
            for col in gdf_nodes.columns:
                if col == "geometry":
                    continue
                gdf_nodes[col] = gdf_nodes[col].apply(
                    lambda x: x[0] if isinstance(x, list) else x
                )
                
            gdf_nodes.to_file(str(NODES_GEOJSON), driver="GeoJSON")
            log.info("Regenerated nodes.geojson with resolved traffic signal tags.")
        except Exception as e:
            log.error(f"Failed during dynamic node processing: {e}")
            if not NODES_GEOJSON.exists():
                raise HTTPException(500, f"Failed to generate nodes GeoJSON: {e}")

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

