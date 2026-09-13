"""
ai/proposal_generator/service_detour_planner.py
─────────────────────────────────────────────────────────────
Road Service / Maintenance Closure — Citizen Detour Route Planner

When a road segment or junction is marked for maintenance:
  1. Loads the OSMnx road graph.
  2. Removes the closed edge(s) or node from the graph.
  3. Computes top-2 alternate citizen detour routes (k-shortest paths).
  4. Calculates citizen impact metrics:
       - Extra travel time (mins)
       - Extra distance (km)
       - Step-by-step road name sequence
       - GeoJSON LineString coordinates for map rendering
  5. Identifies secondary streets that will absorb spillover traffic.
  6. Returns an official Municipal Management Action Plan.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

log = logging.getLogger("service_detour_planner")

ROOT = Path(__file__).resolve().parent.parent.parent
GRAPHML_PATH = ROOT / "data" / "processed" / "network" / "network.graphml"
NODES_PATH   = ROOT / "data" / "processed" / "network" / "nodes.geojson"


def _load_graph():
    try:
        import osmnx as ox
        return ox.load_graphml(str(GRAPHML_PATH))
    except Exception as e:
        log.warning(f"Could not load graph: {e}")
        return None


def _get_road_name(G, u, v) -> str:
    """Extract a human-readable road name from an edge."""
    try:
        data = G.get_edge_data(u, v, 0) or {}
        name = data.get("name", "")
        if isinstance(name, list):
            name = name[0]
        ref = data.get("ref", "")
        if isinstance(ref, list):
            ref = ref[0]
        return name or ref or f"Unnamed Road ({u}→{v})"
    except Exception:
        return "Road"


def _path_to_geojson(G, path_nodes: list) -> dict:
    """Convert a node path to a GeoJSON LineString using node lat/lon."""
    coords = []
    for n in path_nodes:
        node_data = G.nodes.get(n, {})
        lon = node_data.get("x") or node_data.get("lon")
        lat = node_data.get("y") or node_data.get("lat")
        if lon is not None and lat is not None:
            coords.append([float(lon), float(lat)])
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {}
    }


def _path_steps(G, path_nodes: list) -> list[str]:
    """Generate a turn-by-turn road name sequence for the detour."""
    steps = []
    seen = set()
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        road = _get_road_name(G, u, v)
        if road not in seen:
            steps.append(road)
            seen.add(road)
    return steps


def _path_travel_time_s(G, path_nodes: list) -> float:
    """Sum edge travel times along a path (seconds)."""
    total = 0.0
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        data = G.get_edge_data(u, v, 0) or {}
        tt = data.get("travel_time")
        if tt is None:
            length = float(data.get("length", 100))
            speed  = float(data.get("speed_kph", data.get("maxspeed", 30)))
            tt = (length / 1000) / speed * 3600
        total += float(tt)
    return total


def _path_distance_m(G, path_nodes: list) -> float:
    """Sum edge lengths along a path (meters)."""
    total = 0.0
    for i in range(len(path_nodes) - 1):
        u, v = path_nodes[i], path_nodes[i + 1]
        data = G.get_edge_data(u, v, 0) or {}
        total += float(data.get("length", 100))
    return total


def _spillover_roads(G, closed_node: int, detour_path: list, top_n: int = 3) -> list[str]:
    """Identify adjacent secondary streets that will absorb extra traffic."""
    candidate_edges = []
    for n in detour_path[1:-1]:
        for neighbor in list(G.successors(n)) + list(G.predecessors(n)):
            if neighbor not in detour_path and neighbor != closed_node:
                road = _get_road_name(G, n, neighbor)
                highway = (G.get_edge_data(n, neighbor, 0) or {}).get("highway", "")
                if isinstance(highway, list):
                    highway = highway[0]
                if highway in ("residential", "secondary", "tertiary", "unclassified"):
                    candidate_edges.append(road)

    seen = []
    for r in candidate_edges:
        if r not in seen and r != "Road":
            seen.append(r)
        if len(seen) >= top_n:
            break
    return seen


def _municipal_action_plan(
    closure_type: str,
    detour_roads: list[str],
    spillover_roads: list[str],
    duration_days: int = 7,
) -> list[str]:
    """Generate an official traffic & municipal management action plan."""
    steps = [
        f"🚧 ROAD SERVICE ORDER: Estimated closure duration — {duration_days} day{'s' if duration_days != 1 else ''}.",
        f"📋 TRAFFIC POLICE DEPLOYMENT: Station wardens at all entry/exit points of the closed segment.",
    ]
    if detour_roads:
        steps.append(f"🪧 SIGNAGE: Install IRC-standard 'Road Closed — Use Diversion' boards at least 200m before the closure point on all approach roads.")
        steps.append(f"🔀 DIVERSION ROUTE: Citizens should follow — {' → '.join(detour_roads[:5])}.")
    if spillover_roads:
        steps.append(f"⚠️ SECONDARY ROADS UNDER INCREASED LOAD: {', '.join(spillover_roads)} — consider temporary no-parking enforcement on these corridors.")
    if closure_type in ("full", "junction"):
        steps.append("🚌 PUBLIC TRANSPORT: Coordinate with KSRTC/city bus depot to re-route affected bus lines through alternate corridors.")
        steps.append("📣 PUBLIC NOTIFICATION: Issue press note / WhatsApp civic alert 48 hours prior to closure start.")
    steps.append("📱 GOOGLE MAPS / WAZE: Report road closure via Google Maps Local Guides / Waze closure report to update live navigation for citizens automatically.")
    steps.append("🏥 EMERGENCY CORRIDOR: Maintain one emergency vehicle lane (min 3.5m width) at all times per Motor Vehicles Act §119.")
    return steps


def plan_service_detour(
    node_id: int,
    closure_type: str = "full",       # "full" | "partial" | "junction"
    duration_days: int = 7,
    baseline_tt_s: float | None = None,
    source_node: int | None = None,
    target_node: int | None = None,
) -> dict:
    """
    Compute citizen detour routes and municipal action plan for a road service closure.

    Args:
        node_id: The OSM node being closed (junction or road node).
        closure_type: Type of closure — "full", "partial", or "junction".
        duration_days: Estimated duration of the road service.
        baseline_tt_s: Optional baseline travel time (s) before closure for delta comparison.
        source_node: Override source node for routing (default: upstream neighbor).
        target_node: Override target node for routing (default: downstream neighbor).

    Returns:
        Comprehensive detour analysis dict.
    """
    G = _load_graph()
    if G is None:
        return _stub_detour(node_id, closure_type)

    if node_id not in G.nodes:
        return _stub_detour(node_id, closure_type)

    # Select source (upstream) and target (downstream) nodes
    predecessors = list(G.predecessors(node_id))
    successors   = list(G.successors(node_id))

    u = source_node or (predecessors[0] if predecessors else None)
    v = target_node or (successors[0] if successors else None)

    if not u or not v:
        return _stub_detour(node_id, closure_type)

    # Baseline: travel time on the direct route (through the closed node)
    try:
        if baseline_tt_s is None:
            baseline_tt_s = _path_travel_time_s(G, [u, node_id, v])
        baseline_dist_m = _path_distance_m(G, [u, node_id, v])
    except Exception:
        baseline_tt_s   = 120.0
        baseline_dist_m = 300.0

    # Build modified graph with closed node removed
    DG = G.copy()
    try:
        DG.remove_node(node_id)
    except Exception:
        pass

    # Find up to 2 shortest alternate paths
    detour_routes = []
    try:
        if nx.has_path(DG, u, v):
            path = nx.shortest_path(DG, u, v, weight="travel_time")
            detour_routes.append(path)
    except Exception:
        pass

    # Try to find a second distinct detour by removing the first detour's key mid-node
    if len(detour_routes) > 0 and len(detour_routes[0]) > 2:
        try:
            DG2 = DG.copy()
            mid = detour_routes[0][len(detour_routes[0]) // 2]
            DG2.remove_node(mid)
            if nx.has_path(DG2, u, v):
                path2 = nx.shortest_path(DG2, u, v, weight="travel_time")
                if path2 != detour_routes[0]:
                    detour_routes.append(path2)
        except Exception:
            pass

    if not detour_routes:
        return _stub_detour(node_id, closure_type)

    # Build structured detour options
    options = []
    for i, path in enumerate(detour_routes):
        tt_s     = _path_travel_time_s(G, path)
        dist_m   = _path_distance_m(G, path)
        extra_tt = max(0, tt_s - baseline_tt_s)
        extra_km = max(0, (dist_m - baseline_dist_m) / 1000)
        steps    = _path_steps(G, path)
        geojson  = _path_to_geojson(G, path)
        spillover = _spillover_roads(G, node_id, path)

        options.append({
            "route_id":       f"detour_{i + 1}",
            "label":          f"Detour Route {i + 1}" + (" (Recommended)" if i == 0 else " (Alternative)"),
            "path_nodes":     [int(n) for n in path],
            "hops":           len(path) - 1,
            "travel_time_s":  round(tt_s, 1),
            "distance_m":     round(dist_m, 1),
            "extra_time_s":   round(extra_tt, 1),
            "extra_time_min": round(extra_tt / 60, 1),
            "extra_km":       round(extra_km, 2),
            "road_steps":     steps,
            "spillover_roads": spillover,
            "geojson":        geojson,
            "color":          "#06b6d4" if i == 0 else "#f59e0b",
        })

    # Overall spillover summary
    all_spillover = []
    for opt in options:
        for r in opt["spillover_roads"]:
            if r not in all_spillover:
                all_spillover.append(r)

    action_plan = _municipal_action_plan(
        closure_type  = closure_type,
        detour_roads  = options[0]["road_steps"] if options else [],
        spillover_roads = all_spillover,
        duration_days  = duration_days,
    )

    return {
        "node_id":             node_id,
        "closure_type":        closure_type,
        "duration_days":       duration_days,
        "baseline_travel_time_s": round(baseline_tt_s, 1),
        "baseline_distance_m":    round(baseline_dist_m, 1),
        "detour_routes":       options,
        "spillover_roads":     all_spillover,
        "municipal_action_plan": action_plan,
        "citizen_advisory":    (
            f"Due to road service work, please use the recommended alternate route. "
            f"Expected extra travel time: ~{round(options[0]['extra_time_min'], 0):.0f} mins."
            if options else
            "No alternate route found. Please use alternate modes of transport."
        ),
        "google_maps_closure_link": (
            f"https://www.google.com/maps/search/?api=1&query={G.nodes[node_id].get('y', '')},{G.nodes[node_id].get('x', '')}"
            if node_id in G.nodes else None
        ),
    }


def _stub_detour(node_id: int, closure_type: str) -> dict:
    """Fallback stub when the graph isn't loaded."""
    return {
        "node_id": node_id,
        "closure_type": closure_type,
        "duration_days": 7,
        "error": "Road graph not available. Please run simulation first to build the network.",
        "detour_routes": [],
        "municipal_action_plan": [
            "🚧 Close the affected road segment and station traffic wardens.",
            "🪧 Install diversion signage as per IRC:67-2012 standards.",
            "📣 Notify citizens via civic alert systems.",
            "📱 Report closure on Google Maps for automatic navigation update.",
        ],
        "citizen_advisory": "Road service in progress. Please follow on-ground diversion signs.",
        "google_maps_closure_link": None,
    }
