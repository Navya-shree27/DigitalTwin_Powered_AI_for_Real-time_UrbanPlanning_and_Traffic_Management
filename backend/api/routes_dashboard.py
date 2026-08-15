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

    # Auto-recover runs that are truly stale (finished but DB status never updated).
    # Only trigger if the run has telemetry data ready OR is more than 30 minutes old.
    # SUMO needs ~50s just to load the network, so never kill a young run.
    if run.status in ["running", "pending"]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        created_at = run.created_at.replace(tzinfo=timezone.utc) if run.created_at and run.created_at.tzinfo is None else run.created_at
        age_seconds = (now - created_at).total_seconds() if created_at else 0

        has_telemetry = bool(run.get_telemetry())
        # Only recover if telemetry exists (sim truly completed) OR if truly stale (>30 min)
        if has_telemetry or age_seconds > 1800:
            run.status = "done" if has_telemetry else "failed"
            run.finished_at = now
            db.add(run)
            db.commit()
            log.info(f"Auto-recovered stale run {run.id} -> new status: {run.status}")

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


_GEOJSON_CACHE: dict[str, bytes] = {}

@router.get("/api/dashboard/{scenario_id}/geojson/network")
def get_network_geojson(scenario_id: int):
    """Serve the road network GeoJSON for map rendering (cached in RAM for speed)."""
    scenario_dir = ROOT / "data" / "processed" / "network" / str(scenario_id)
    path = scenario_dir / "network.geojson"

    # Self-healing fallback: if scenario-specific network files don't exist, build them
    if not path.exists():
        from backend.database.db_connector import SessionLocal
        from backend.models.schema import Scenario
        db = SessionLocal()
        try:
            scenario = db.query(Scenario).get(scenario_id)
            if scenario:
                log.info(f"Self-healing: Auto-building scenario-specific network for Scenario {scenario_id} ({scenario.city})")
                from simulation.osm_to_network import build_network
                build_network(city=scenario.city, scenario_id=scenario_id)
        except Exception as e:
            log.warning(f"Failed auto-building network for scenario {scenario_id}: {e}")
        finally:
            db.close()

    # Fallback to global if still doesn't exist
    if not path.exists():
        path = NETWORK_GEOJSON

    if not path.exists():
        raise HTTPException(404, "Network GeoJSON not found.")

    cache_key = f"network_{scenario_id}_{path.stat().st_mtime}"
    if cache_key not in _GEOJSON_CACHE:
        with open(path, "rb") as f:
            _GEOJSON_CACHE[cache_key] = f.read()

    from fastapi import Response
    return Response(content=_GEOJSON_CACHE[cache_key], media_type="application/geo+json")

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate Great Circle distance in km between two lat/lon points."""
    import math
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/api/dashboard/{scenario_id}/geojson/nodes")
def get_nodes_geojson(scenario_id: int):
    """Serve node (intersection) GeoJSON for marker rendering (cached in RAM)."""
    scenario_dir = ROOT / "data" / "processed" / "network" / str(scenario_id)
    path = scenario_dir / "nodes.geojson"
    graphml_path = scenario_dir / "network.graphml"

    if not path.exists():
        # Fallback pathing
        path = NODES_GEOJSON
        graphml_path = ROOT / "data" / "processed" / "network" / "network.graphml"

    if not path.exists():
        raise HTTPException(404, "Nodes GeoJSON not found.")

    cache_key = f"nodes_{scenario_id}_{path.stat().st_mtime}"
    if cache_key not in _GEOJSON_CACHE:
        try:
            with open(path, "r", encoding="utf-8") as f_nodes:
                nodes_data = json.load(f_nodes)

            features = nodes_data.get("features", [])

            # Extract signals from city_signals.geojson (extremely fast, avoids parsing huge GraphML files)
            signal_osmids: set[str] = set()
            signals_path = scenario_dir / "city_signals.geojson"
            if signals_path.exists():
                try:
                    with open(signals_path, "r", encoding="utf-8") as f_sigs:
                        sigs_data = json.load(f_sigs)
                    for feat in sigs_data.get("features", []):
                        osmid = feat.get("properties", {}).get("osmid")
                        if osmid:
                            signal_osmids.add(str(osmid))
                except Exception as sigs_err:
                    log.warning(f"Could not load city_signals.geojson to extract signal osmids: {sigs_err}")

            # Overpass fallback / proximity mapping signals
            mapping_path = ROOT / "data" / "node_mapping.json"
            coord_signals: list[dict] = []
            if mapping_path.exists():
                try:
                    with open(mapping_path, "r", encoding="utf-8") as fm:
                        coord_signals = json.load(fm)
                except Exception:
                    pass
            
            PROXIMITY_KM = 0.08  # 80 metres — tight match threshold
            
            for feat in features:
                props = feat.get("properties", {})
                geom = feat.get("geometry", {})
                osmid_str = str(props.get("osmid", ""))
                
                # Check signal set first (most reliable)
                if osmid_str in signal_osmids:
                    if props.get("highway") != "traffic_signals":
                        props["highway"] = "traffic_signals"
                        props["designation"] = f"Signal · {osmid_str}"
                    continue
                
                # Fallback: proximity match to node_mapping.json coordinates
                if geom.get("type") == "Point" and coord_signals:
                    coords = geom.get("coordinates", [])
                    if len(coords) >= 2:
                        feat_lon, feat_lat = coords[0], coords[1]
                        for sig in coord_signals:
                            dist = _haversine_km(feat_lat, feat_lon, sig["lat"], sig["lon"])
                            if dist < PROXIMITY_KM:
                                if props.get("highway") != "traffic_signals":
                                    props["highway"] = "traffic_signals"
                                    props["designation"] = sig.get("name", f"Signal · {osmid_str}")
                                break

            # Save directly to memory cache to prevent uvicorn file-watch restart loops on write
            _GEOJSON_CACHE[cache_key] = json.dumps(nodes_data, separators=(",", ":")).encode()

        except Exception as e:
            log.error(f"Error injecting signal data into nodes GeoJSON: {e}")
            try:
                with open(path, "rb") as f:
                    _GEOJSON_CACHE[cache_key] = f.read()
            except Exception:
                pass

    from fastapi import Response
    return Response(content=_GEOJSON_CACHE[cache_key], media_type="application/geo+json")


@router.get("/api/dashboard/{scenario_id}/telemetry")
def get_telemetry(scenario_id: int, db: Session = Depends(get_db)) -> dict:
    """Get the telemetry of the latest completed run of the scenario."""
    run = _latest_done_run(scenario_id, db)
    if not run:
        raise HTTPException(404, f"No completed run for scenario {scenario_id}.")
    return run.get_telemetry()


# ── Real traffic signal locations from OSM ────────────────────────────────────
# These are cached to disk after first fetch so subsequent loads are instant.

_SIGNALS_CACHE_PATH = ROOT / "data" / "city_signals.geojson"

# Known Davanagere city-centre traffic signal coordinates (from OSM/field data).
# Used as instant fallback if Overpass API is unreachable.
# Known Davanagere city-centre traffic signal coordinates strictly matching graph nodes (from OSM/field data).
# Used as instant fallback if Overpass API is unreachable.
_DAVANAGERE_SIGNALS_FALLBACK = [
    {"osmid": 571395243,  "name": "Aruna Theatre Junction",     "lat": 14.4678344, "lon": 75.9145766, "street_count": 4},
    {"osmid": 571407773,  "name": "Vidyarthi Bhavan Junction",  "lat": 14.4592308, "lon": 75.9198481, "street_count": 3},
    {"osmid": 1470841066, "name": "Mothi Circle (PB Road)",     "lat": 14.4643372, "lon": 75.9176024, "street_count": 3},
    {"osmid": 1465243476, "name": "Gandhi Circle",              "lat": 14.4653704, "lon": 75.9226860, "street_count": 3},
    {"osmid": 1822610272, "name": "District Court Junction",    "lat": 14.4623246, "lon": 75.9202939, "street_count": 3},
    {"osmid": 1782305061, "name": "8th Main / PB Road Signal",  "lat": 14.4638584, "lon": 75.9155572, "street_count": 3},
    {"osmid": 2702258541, "name": "KSRTC Bus Stand Junction",   "lat": 14.4675753, "lon": 75.9157590, "street_count": 3},
    {"osmid": 1782236061, "name": "Vinobanagar Circle",         "lat": 14.4555871, "lon": 75.9149393, "street_count": 3},
    {"osmid": 1464736528, "name": "SBI / Collector Office",     "lat": 14.4639857, "lon": 75.9199356, "street_count": 3},
    {"osmid": 1782269831, "name": "Anjaneya Temple Road",       "lat": 14.4606020, "lon": 75.9220397, "street_count": 3},
]


def _build_signals_geojson(signals: list[dict]) -> dict:
    """Convert a list of signal dicts to a GeoJSON FeatureCollection."""
    features = []
    for sig in signals:
        feat = {
            "type": "Feature",
            "properties": {
                "osmid": sig.get("osmid"),
                "highway": "traffic_signals",
                "designation": sig.get("name", ""),
                "street_count": sig.get("street_count", 3),
                "name": sig.get("name", ""),
            },
            "geometry": {
                "type": "Point",
                "coordinates": [sig["lon"], sig["lat"]],
            },
        }
        features.append(feat)
    return {"type": "FeatureCollection", "features": features}


def _fetch_overpass_signals(scenario_id: int) -> list[dict]:
    """Query Overpass API for traffic signals in the city bbox, return list of dicts."""
    import urllib.request
    import urllib.parse

    # Use the scenario's city bbox from scenario-specific network_meta.json first, fall back to global
    scenario_meta_path = ROOT / "data" / "processed" / "network" / str(scenario_id) / "network_meta.json"
    meta_path = scenario_meta_path if scenario_meta_path.exists() else (ROOT / "data" / "processed" / "network" / "network_meta.json")

    if meta_path.exists():
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
            bbox_full = meta.get("bbox", {})
            # Narrow to city-centre: use the middle 30% of the bbox
            n, s, e, w = bbox_full.get("north", 14.49), bbox_full.get("south", 14.43), bbox_full.get("east", 75.96), bbox_full.get("west", 75.89)
            lat_mid = (n + s) / 2
            lon_mid = (e + w) / 2
            lat_range = (n - s) * 0.18   # ±18% of total range → city centre strip
            lon_range = (e - w) * 0.18
            bbox = f"{lat_mid - lat_range},{lon_mid - lon_range},{lat_mid + lat_range},{lon_mid + lon_range}"
        except Exception:
            bbox = "14.43,75.89,14.49,75.96"
    else:
        bbox = "14.43,75.89,14.49,75.96"

    query = f"""
[out:json][timeout:25];
(
  node["highway"="traffic_signals"]({bbox});
  node["highway"="crossing"]["crossing"="traffic_signals"]({bbox});
);
out body;
"""
    payload = ("data=" + urllib.parse.quote(query)).encode()
    req = urllib.request.Request(
        "https://overpass-api.de/api/interpreter",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "DigitalTwin-TrafficAI/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    signals = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        signals.append({
            "osmid": el["id"],
            "lat":   el["lat"],
            "lon":   el["lon"],
            "name":  tags.get("name") or tags.get("ref") or f"Signal #{el['id']}",
            "street_count": 3,
        })
    return signals


@router.get("/api/dashboard/{scenario_id}/geojson/signals")
def get_signals_geojson(scenario_id: int, refresh: bool = False):
    """
    Serve traffic signal locations as GeoJSON strictly snapped to graph node coordinates.
    """
    from fastapi import Response

    scenario_dir = ROOT / "data" / "processed" / "network" / str(scenario_id)
    scenario_dir.mkdir(parents=True, exist_ok=True)
    signals_cache_path = scenario_dir / "city_signals.geojson"

    # Return disk cache unless caller forces a refresh or cache has outdated synthetic dummy IDs
    if not refresh and signals_cache_path.exists():
        try:
            with open(signals_cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            feats = cached_data.get("features", [])
            if feats and len(feats) > 0:
                has_dummy = any(feat.get("properties", {}).get("osmid", 0) >= 100000000 for feat in feats)
                if not has_dummy:
                    return Response(content=json.dumps(cached_data).encode(), media_type="application/geo+json")
        except Exception as e:
            log.warning(f"Error reading signals cache: {e}")

    # Build snapped signals directly from the scenario's nodes.geojson
    nodes_path = scenario_dir / "nodes.geojson"
    if not nodes_path.exists():
        nodes_path = NODES_GEOJSON

    node_features = []
    if nodes_path.exists():
        try:
            with open(nodes_path, "r", encoding="utf-8") as f_nodes:
                nodes_data = json.load(f_nodes)
                node_features = nodes_data.get("features", [])
        except Exception as e:
            log.warning(f"Failed to read nodes.geojson: {e}")

    # Build lookup table of graph nodes: osmid_str -> (lat, lon, props)
    nodes_by_osmid = {}
    node_coords = []
    for feat in node_features:
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        osmid = props.get("osmid")
        if osmid and geom.get("type") == "Point":
            coords = geom.get("coordinates", [])
            if len(coords) >= 2:
                lon, lat = coords[0], coords[1]
                nodes_by_osmid[str(osmid)] = (lat, lon, props)
                node_coords.append((str(osmid), lat, lon, props))

    # Try live Overpass fetch or fallback list
    raw_signals = []
    try:
        raw_signals = _fetch_overpass_signals(scenario_id)
    except Exception as e:
        log.warning(f"Overpass API unavailable ({e}), using fallback signal list.")

    if not raw_signals:
        raw_signals = _DAVANAGERE_SIGNALS_FALLBACK

    signal_features = []
    used_osmids = set()

    # 1. First add nodes that already have highway == 'traffic_signals' in nodes.geojson
    for str_id, lat, lon, props in node_coords:
        if props.get("highway") == "traffic_signals":
            used_osmids.add(str_id)
            signal_features.append({
                "type": "Feature",
                "properties": {
                    "osmid": props.get("osmid"),
                    "highway": "traffic_signals",
                    "designation": props.get("designation") or props.get("name") or f"Signal · Node {props.get('osmid')}",
                    "street_count": props.get("street_count", 3),
                    "name": props.get("name") or props.get("designation") or f"Signal · Node {props.get('osmid')}",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [lon, lat]
                }
            })

    # 2. Match raw signals to graph nodes: match by direct osmid if present, or snap to nearest major intersection node
    for sig in raw_signals:
        sig_lat = sig.get("lat")
        sig_lon = sig.get("lon")
        sig_name = sig.get("name") or f"Signal #{sig.get('osmid', '?')}"
        if sig_lat is None or sig_lon is None:
            continue

        osmid_key = str(sig.get("osmid", ""))
        matched_osmid = None

        if osmid_key in nodes_by_osmid:
            matched_osmid = osmid_key
        elif node_coords:
            # Spatial nearest search preferring major intersection nodes (street_count >= 3)
            best_dist = float("inf")
            for node_id, n_lat, n_lon, n_props in node_coords:
                st_count = n_props.get("street_count", 1)
                d = _haversine_km(sig_lat, sig_lon, n_lat, n_lon)
                # Prioritize major intersection nodes over dead-end nodes
                effective_dist = d if st_count >= 3 else d * 2.5
                if effective_dist < best_dist:
                    best_dist = effective_dist
                    matched_osmid = node_id

        if matched_osmid and matched_osmid not in used_osmids:
            used_osmids.add(matched_osmid)
            node_lat, node_lon, node_props = nodes_by_osmid[matched_osmid]
            signal_features.append({
                "type": "Feature",
                "properties": {
                    "osmid": node_props.get("osmid"),
                    "highway": "traffic_signals",
                    "designation": sig_name,
                    "street_count": node_props.get("street_count", 3),
                    "name": sig_name,
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [node_lon, node_lat]
                }
            })

    geojson = {"type": "FeatureCollection", "snapped": True, "features": signal_features}
    content = json.dumps(geojson, separators=(",", ":")).encode()

    try:
        with open(signals_cache_path, "wb") as f:
            f.write(content)
    except Exception as e:
        log.warning(f"Could not save signals cache: {e}")

    return Response(content=content, media_type="application/geo+json")

