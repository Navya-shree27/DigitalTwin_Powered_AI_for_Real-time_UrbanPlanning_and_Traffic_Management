"""
simulation/simulation_runner.py
───────────────────────────────
Orchestrates a complete simulation run end-to-end.

Simulation engines
──────────────────
• "synthetic"  — generates realistic synthetic traffic telemetry from the
                 OSMnx graph topology.  No external tools required.
                 Used in Phase A as a working placeholder.
• "sumo"       — delegates to traci_interface.py which controls a live SUMO
                 process.  Requires SUMO to be installed.
• "cityflow"   — delegates to a CityFlow runner (Phase B+).

Output schema (telemetry dict)
──────────────────────────────
{
  "scenario_id": int,
  "engine": str,
  "duration_s": int,
  "seed": int,
  "generated_at": str,
  "edges": [
    {
      "edge_id": str,          # "{u}_{v}_{k}"
      "u": int, "v": int,
      "length_m": float,
      "road_type": str,
      "lanes": int,
      "speed_kph": float,       # free-flow speed
      "capacity": int,
      "flow": float,            # simulated vehicles / hour
      "speed_sim": float,       # simulated avg speed (km/h)
      "density": float,         # vehicles / km
      "queue_length": float,    # avg queue length (vehicles)
      "wait_time": float,       # avg wait time per vehicle (s)
      "travel_time": float,     # simulated avg travel time (s)
      "occupancy": float,       # fraction 0–1
    }, ...
  ],
  "nodes": [
    {
      "node_id": int,
      "lat": float, "lon": float,
      "street_count": int,
      "conflict_rate": float,   # simulated conflicts / hour
      "avg_wait_time": float,   # avg wait time at this intersection (s)
    }, ...
  ],
  "summary": {
    "avg_travel_time_s": float,
    "avg_wait_time_s": float,
    "avg_speed_kph": float,
    "total_flow_veh_h": float,
    "congested_edges": int,
    "congestion_ratio": float,
  }
}
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import osmnx as ox
from dotenv import load_dotenv

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROCESSED_DIR = ROOT / "data" / "processed" / "network"

log = logging.getLogger("simulation_runner")


# ─────────────────────────────────────────────────────────────────────────────
# Graph loading
# ─────────────────────────────────────────────────────────────────────────────

def load_graph(scenario_id: int | None = None) -> nx.MultiDiGraph:
    """Load the processed road network GraphML, building it first if absent."""
    if scenario_id:
        scenario_dir = PROCESSED_DIR / str(scenario_id)
        graphml_path = scenario_dir / "network.graphml"
        if not graphml_path.exists():
            log.info(f"No processed network found for scenario {scenario_id} — querying city name from DB …")
            from backend.database.db_connector import SessionLocal
            from backend.models.schema import Scenario
            db = SessionLocal()
            try:
                scenario = db.query(Scenario).get(scenario_id)
                if scenario:
                    log.info(f"Auto-building network for scenario {scenario_id} ({scenario.city}) …")
                    from simulation.osm_to_network import build_network
                    build_network(city=scenario.city, scenario_id=scenario_id)
            except Exception as e:
                log.warning(f"Could not automatically build network for scenario {scenario_id}: {e}")
            finally:
                db.close()
    else:
        graphml_path = PROCESSED_DIR / "network.graphml"

    # Default fallback to global if still doesn't exist
    if not graphml_path.exists():
        graphml_path = PROCESSED_DIR / "network.graphml"

    if not graphml_path.exists():
        log.info("No processed network found — triggering default osm_to_network build …")
        from simulation.osm_to_network import build_network
        build_network()

    log.info(f"Loading graph from {graphml_path}")
    G = ox.load_graphml(str(graphml_path))
    
    # Synchronize graph G nodes with the 10 real-world target signals
    target_ids = [571395243, 571407773, 1470841066, 1465243476, 1822610272, 1782305061, 2702258541, 1782236061, 1464736528, 1782269831]
    for tid in target_ids:
        tid_str = str(tid)
        found_key = None
        if tid_str in G.nodes:
            found_key = tid_str
        elif tid in G.nodes:
            found_key = tid
            
        if found_key is not None:
            G.nodes[found_key]["highway"] = "traffic_signals"
            
    return G


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic telemetry generator
# ─────────────────────────────────────────────────────────────────────────────

class SyntheticSimulator:
    """
    Generates realistic synthetic traffic telemetry from graph topology.

    The synthetic model:
      - Uses a time-of-day demand multiplier (peak hour, off-peak, etc.)
      - Assigns flow as a fraction of capacity, modulated by connectivity
        (high-degree nodes → higher demand) and random noise
      - Derives speed, density, queue, wait from flow using the
        BPR (Bureau of Public Roads) speed–flow curve:
            travel_time = free_flow_tt × [1 + α × (flow/capacity)^β]
        with α=0.15, β=4  (standard BPR defaults)
    """

    BPR_ALPHA = 0.15
    BPR_BETA  = 4.0

    def __init__(self, G: nx.MultiDiGraph, duration_s: int, seed: int, apply_proposals: list[dict] | None = None):
        self.G = G
        self.duration_s = duration_s
        self.apply_proposals = apply_proposals or []
        np.random.seed(seed)
        random.seed(seed)
        self._degree_cache: dict[int, int] = dict(G.degree())

    # ── Demand multiplier ─────────────────────────────────────────────────────

    def _demand_multiplier(self) -> float:
        """
        Simulate a 'peak hour' demand: returns a value between 0.3 and 1.0
        representing the overall demand level for this run.
        Currently sampled uniformly; in Phase B this will be driven by a
        real demand scenario file.
        """
        return float(np.random.uniform(0.55, 0.90))

    # ── BPR speed–flow ────────────────────────────────────────────────────────

    def _bpr_travel_time(self, free_flow_tt: float, flow: float, capacity: float) -> float:
        ratio = flow / max(capacity, 1)
        return free_flow_tt * (1 + self.BPR_ALPHA * ratio ** self.BPR_BETA)

    # ── Edge simulation ───────────────────────────────────────────────────────

    def _simulate_edges(self, demand_mult: float) -> list[dict]:
        records = []
        for u, v, k, data in self.G.edges(data=True, keys=True):
            edge_id = f"{u}_{v}_{k}"

            length_m  = float(data.get("length", 100))
            speed_kph = float(data.get("speed_kph", 40))
            capacity  = float(data.get("capacity", 800))
            lanes     = int(data.get("lanes", 1))
            road_type = str(data.get("road_type", "unclassified"))

            free_flow_tt = (length_m / 1000) / speed_kph * 3600  # seconds

            # Degree-weighted base demand (vehicles/hour): busier nodes -> higher demand
            avg_degree   = (self._degree_cache.get(u, 2) + self._degree_cache.get(v, 2)) / 2
            degree_scale = min(avg_degree / 4.0, 1.0)
            noise        = float(np.random.normal(0, 0.08))

            # Base demand volume (veh/h) independent of edge capacity
            demand_ratio   = float(np.clip(demand_mult * degree_scale + noise, 0.15, 1.25))
            traffic_demand = demand_ratio * 900.0  # vehicles / hour demand

            # Apply edge demand modifier if route diversion proposal applied
            demand_modifier = float(data.get("demand_modifier", 1.0))
            flow = max(10.0, traffic_demand * demand_modifier)

            # BPR speed-flow curve: travel time increases nonlinearly with flow/capacity ratio
            sim_tt    = self._bpr_travel_time(free_flow_tt, flow, capacity)
            sim_speed = (length_m / 1000.0) / (sim_tt / 3600.0) if sim_tt > 0 else speed_kph

            # Derived metrics
            density   = flow / max(sim_speed, 1.0)  # veh/km
            flow_ratio = flow / max(capacity, 1.0)
            queue     = max(0.0, (flow_ratio - 0.75) * capacity * 0.02)  # veh
            wait_time = max(0.0, (sim_tt - free_flow_tt) + float(np.random.exponential(1.5)))
            occupancy = float(np.clip(flow_ratio, 0.0, 1.0))

            records.append({
                "edge_id":      edge_id,
                "u":            int(u),
                "v":            int(v),
                "length_m":     round(length_m, 1),
                "road_type":    road_type,
                "lanes":        lanes,
                "speed_kph":    round(speed_kph, 1),
                "capacity":     int(capacity),
                "flow":         round(flow, 2),
                "speed_sim":    round(max(sim_speed, 1.0), 2),
                "density":      round(density, 3),
                "queue_length": round(queue, 2),
                "wait_time":    round(wait_time, 2),
                "travel_time":  round(sim_tt, 2),
                "occupancy":    round(occupancy, 4),
            })
        return records

    # ── Node simulation ───────────────────────────────────────────────────────

    def _simulate_nodes(self, edge_records: list[dict]) -> list[dict]:
        # Index incoming flows per node
        node_flows: dict[int, list[float]] = {}
        for e in edge_records:
            node_flows.setdefault(e["v"], []).append(e["flow"])

        records = []
        for node_id, data in self.G.nodes(data=True):
            lat = float(data.get("y", 0))
            lon = float(data.get("x", 0))
            sc  = int(self._degree_cache.get(node_id, 1))

            in_flows = node_flows.get(node_id, [0])
            avg_flow = np.mean(in_flows)

            conflict_rate = float(np.clip(
                avg_flow * sc / 3000 + np.random.exponential(0.05), 0, 5
            ))

            # Calculate wait modifier based on applied signal timing proposals
            wait_modifier = 1.0
            for p in self.apply_proposals:
                ptype = p.get("type", "")
                p_node = p.get("node_id") or p.get("node") or p.get("location", {}).get("node_id")
                if ptype == "signal_timing" and p_node is not None and int(p_node) == int(node_id):
                    imp = p.get("expected_improvement", {})
                    reduction = float(imp.get("expected_wait_reduction_pct", 25))
                    wait_modifier *= (1.0 - reduction / 100.0)

            avg_wait = float(np.clip(
                (np.random.gamma(2, scale=5) + (avg_flow / 1000 * 8)) * wait_modifier, 0, 120
            ))

            has_sidewalk = False
            for u_e, v_e, k_e, edata in self.G.edges(data=True, keys=True):
                if u_e == node_id or v_e == node_id:
                    if edata.get("sidewalk_width", 0.0) > 0.0:
                        has_sidewalk = True
                        break

            records.append({
                "node_id":      int(node_id),
                "lat":          round(lat, 6),
                "lon":          round(lon, 6),
                "street_count": sc,
                "conflict_rate": round(conflict_rate, 3),
                "avg_wait_time": round(avg_wait, 2),
                "highway":       data.get("highway"),
                "designation":   data.get("designation"),
                "has_sidewalk":  has_sidewalk,
                "has_dustbin":   data.get("has_dustbin", False),
            })
        return records

    # ── Summary ───────────────────────────────────────────────────────────────

    def _compute_summary(self, edges: list[dict], nodes: list[dict]) -> dict:
        speeds  = [e["speed_sim"] for e in edges]
        waits   = [e["wait_time"] for e in edges]
        tts     = [e["travel_time"] for e in edges]
        flows   = [e["flow"] for e in edges]
        congested = sum(1 for e in edges if e["occupancy"] > 0.75)
        return {
            "avg_travel_time_s":  round(float(np.mean(tts)), 2),
            "avg_wait_time_s":    round(float(np.mean(waits)), 2),
            "avg_speed_kph":      round(float(np.mean(speeds)), 2),
            "total_flow_veh_h":   round(float(np.sum(flows)), 0),
            "congested_edges":    congested,
            "congestion_ratio":   round(congested / max(len(edges), 1), 4),
        }

    # ── Run ───────────────────────────────────────────────────────────────────

    def run(self) -> dict:
        log.info("Running synthetic simulation …")
        t0 = time.time()
        demand_mult = self._demand_multiplier()
        edges = self._simulate_edges(demand_mult)
        nodes = self._simulate_nodes(edges)
        summary = self._compute_summary(edges, nodes)
        elapsed = time.time() - t0
        log.info(
            f"Synthetic simulation complete in {elapsed:.2f}s — "
            f"{len(edges)} edges, {len(nodes)} nodes. "
            f"Congestion ratio: {summary['congestion_ratio']:.1%}"
        )
        return {
            "engine": "synthetic",
            "demand_multiplier": round(demand_mult, 3),
            "edges": edges,
            "nodes": nodes,
            "summary": summary,
        }


# ─────────────────────────────────────────────────────────────────────────────
# SUMO / CityFlow stubs
# ─────────────────────────────────────────────────────────────────────────────

def _run_sumo(G: nx.MultiDiGraph, duration_s: int, seed: int, scenario_id: int | None = None) -> dict:
    """Delegate to traci_interface once SUMO is installed."""
    from simulation.traci_interface import SUMOTraCIInterface
    iface = SUMOTraCIInterface(G, duration_s, seed, scenario_id)
    return iface.run()


def _run_cityflow(G: nx.MultiDiGraph, duration_s: int, seed: int) -> dict:
    raise NotImplementedError("CityFlow integration is planned for Phase B.")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def run_simulation(
    scenario_id: int,
    engine: str | None = None,
    duration_s: int | None = None,
    seed: int | None = None,
    apply_proposals: list[dict] | None = None,
    G: nx.MultiDiGraph | None = None,
) -> dict:
    """
    Run a traffic simulation for *scenario_id* and return the full telemetry
    dict (see module docstring for schema).

    Parameters
    ──────────
    scenario_id     : DB id of the scenario being simulated.
    engine          : "synthetic" | "sumo" | "cityflow" (defaults to .env).
    duration_s      : Simulation window in seconds (defaults to .env).
    seed            : Random seed for reproducibility.
    apply_proposals : Optional list of proposal dicts to apply before
                      running (for validation/re-simulation).
    G               : Optional pre-loaded or modified NetworkX road network graph.
    """
    engine     = engine     or os.getenv("SIMULATION_ENGINE", "synthetic")
    duration_s = duration_s or int(os.getenv("SIMULATION_DURATION", "3600"))
    seed       = seed       or int(os.getenv("SIMULATION_SEED", "42"))

    log.info(f"Starting simulation — scenario={scenario_id}, engine={engine}, duration={duration_s}s, seed={seed}")

    if G is None:
        G = load_graph(scenario_id)

    # Apply any proposals to the graph (e.g. speed/lane changes)
    if apply_proposals:
        G = _apply_proposals_to_graph(G, apply_proposals)

    if engine == "synthetic":
        result = SyntheticSimulator(G, duration_s, seed, apply_proposals).run()
    elif engine == "sumo":
        result = _run_sumo(G, duration_s, seed, scenario_id)
    elif engine == "cityflow":
        result = _run_cityflow(G, duration_s, seed)
    else:
        raise ValueError(f"Unknown engine: {engine!r}")

    result.update({
        "scenario_id":    scenario_id,
        "duration_s":     duration_s,
        "seed":           seed,
        "generated_at":   __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "proposals_applied": apply_proposals or [],
    })
    return result


def _apply_proposals_to_graph(
    G: nx.MultiDiGraph, proposals: list[dict]
) -> nx.MultiDiGraph:
    """
    Apply a list of proposals to graph attributes before simulation.
    Supported proposal types:
      - signal_timing  : modifies node wait times
      - lane_change    : modifies edge lane count / capacity / speed
      - route_diversion: redirects traffic demand from congested corridors
    """
    G = G.copy()
    for p in proposals:
        ptype = p.get("type", "")
        if ptype == "lane_change":
            edge = p.get("edge") or p.get("congested_edge") or p.get("location", {}).get("edge_id")
            action = p.get("action", "")
            if edge and "_" in str(edge):
                parts = str(edge).split("_")
                if len(parts) >= 2:
                    try:
                        u, v = int(parts[0]), int(parts[1])
                        if G.has_edge(u, v):
                            for k in G[u][v]:
                                cur_lanes = int(G[u][v][k].get("lanes", 1))
                                if action == "ADD_LANE" or "new_lanes" in p:
                                    new_lanes = int(p.get("new_lanes", cur_lanes + 1))
                                    G[u][v][k]["lanes"] = new_lanes
                                    G[u][v][k]["capacity"] = new_lanes * 900
                                elif action == "REMOVE_LANE":
                                    new_lanes = int(p.get("new_lanes", max(1, cur_lanes - 1)))
                                    G[u][v][k]["lanes"] = new_lanes
                                    G[u][v][k]["capacity"] = new_lanes * 900
                                elif action == "REPURPOSE_LANE":
                                    # Dynamic tidal flow / transit lane increases capacity & speed
                                    G[u][v][k]["capacity"] = int(G[u][v][k].get("capacity", cur_lanes * 900) * 1.30)
                                    G[u][v][k]["speed_kph"] = float(G[u][v][k].get("speed_kph", 40.0)) * 1.15
                    except (ValueError, KeyError):
                        pass

        elif ptype == "route_diversion":
            edge = p.get("congested_edge") or p.get("edge") or p.get("location", {}).get("edge_id")
            if edge and "_" in str(edge):
                parts = str(edge).split("_")
                try:
                    u, v = int(parts[0]), int(parts[1])
                    if G.has_edge(u, v):
                        for k in G[u][v]:
                            # Divert demand away from congested edge (reduces flow on this edge)
                            G[u][v][k]["demand_modifier"] = 0.60
                            G[u][v][k]["capacity"] = int(G[u][v][k].get("capacity", 800) * 1.20)
                except (ValueError, KeyError):
                    pass

    return G
