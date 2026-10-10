"""
ml/dataset_generator.py
────────────────────────
Simulation-based Traffic Dataset Generator for Genuine Future Traffic Prediction.

IMPORTANT NOTICE:
This module generates a SYNTHETIC / SIMULATION-GENERATED traffic dataset
derived from the OSMnx road network topology and dynamic Bureau of Public Roads (BPR)
speed-flow modeling across consecutive time intervals t = 1, ..., T.

Formulation (Zero Target Leakage):
──────────────────────────────────
Input Features at Time t:
  - Current Telemetry: flow(t), speed_sim(t), density(t), queue_length(t), wait_time(t), occupancy(t), speed_ratio(t)
  - Lagged Telemetry: flow(t-1), speed_sim(t-1), occupancy(t-1), queue_length(t-1)
  - Momentum / Deltas: Δflow = flow(t)-flow(t-1), Δoccupancy = occ(t)-occ(t-1), Δspeed = speed(t)-speed(t-1)
  - Static Topology: length_m, lanes, speed_kph (free-flow), capacity, road_type, widenable
  - Temporal Context: time_step, scenario_demand(t)

Target at Future Time t+1:
  - congestion_level(t+1): 0 (Low), 1 (Moderate), 2 (Severe)
  - congestion_score(t+1): Continuous score (0.0 to 1.0)

Usage:
──────
    python -m ml.dataset_generator --scenarios 25 --timesteps 12 --output data/processed/simulation_traffic_dataset.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
NETWORK_DIR = PROCESSED_DIR / "network"
DEFAULT_OUTPUT = PROCESSED_DIR / "simulation_traffic_dataset.csv"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dataset_generator")


def load_network_graph() -> nx.MultiDiGraph:
    """Load or generate the base network graph."""
    import osmnx as ox
    graphml_path = NETWORK_DIR / "network.graphml"
    if not graphml_path.exists():
        log.info("No processed network found. Building network via osm_to_network...")
        from simulation.osm_to_network import build_network
        build_network()
    return ox.load_graphml(str(graphml_path))


def calculate_congestion_labels(
    occupancy: float,
    speed_ratio: float,
    queue_length: float,
    wait_time: float,
) -> tuple[int, str, float]:
    """
    Classify congestion state according to HCM Level of Service criteria.
    """
    occ_norm = np.clip(occupancy, 0.0, 1.2)
    speed_loss = np.clip(1.0 - speed_ratio, 0.0, 1.0)
    delay_factor = np.clip(wait_time / 60.0, 0.0, 1.0)

    congestion_score = float(0.50 * occ_norm + 0.35 * speed_loss + 0.15 * delay_factor)
    congestion_score = round(float(np.clip(congestion_score, 0.0, 1.0)), 4)

    if speed_ratio < 0.45 or occupancy > 0.78 or queue_length > 8.0:
        label = 2
        label_name = "Severe"
    elif speed_ratio < 0.70 or occupancy > 0.50 or queue_length > 3.0:
        label = 1
        label_name = "Moderate"
    else:
        label = 0
        label_name = "Low"

    return label, label_name, congestion_score


def simulate_scenario_timeseries(
    G: nx.MultiDiGraph,
    scenario_idx: int,
    peak_demand: float,
    n_timesteps: int,
    seed: int,
) -> list[dict[str, Any]]:
    """
    Simulate time-series traffic evolution over n_timesteps (e.g. 15-min intervals)
    following a diurnal rush-hour bell curve with stochastic fluctuations and shockwaves.
    """
    np.random.seed(seed)
    random.seed(seed)
    degree_cache = dict(G.degree())

    bpr_alpha = 0.15
    bpr_beta = 4.0

    edges = list(G.edges(data=True, keys=True))
    n_edges = len(edges)

    # Diurnal demand curve profile across timesteps: e.g. rises to peak then subsides
    t_steps = np.linspace(0, np.pi, n_timesteps)
    demand_curve = peak_demand * (0.40 + 0.60 * np.sin(t_steps))

    # Initialize previous state tracking for each edge
    # edge_id -> {flow, speed_sim, occupancy, queue_length}
    prev_state: dict[str, dict[str, float]] = {}

    # Store full trajectory of raw measurements per timestep
    raw_trajectory: list[dict[str, dict[str, Any]]] = []

    for t_idx in range(n_timesteps):
        t_demand = float(demand_curve[t_idx])
        step_measurements: dict[str, dict[str, Any]] = {}

        for u, v, k, data in edges:
            edge_id = f"{u}_{v}_{k}"
            length_m = float(data.get("length", 120.0))
            speed_kph = float(data.get("speed_kph", 40.0))
            capacity = float(data.get("capacity", 800.0))
            lanes = int(data.get("lanes", 1))
            road_type = str(data.get("road_type", data.get("highway", "unclassified")))
            widenable = bool(data.get("widenable", True))

            free_flow_tt = (length_m / 1000.0) / max(speed_kph, 5.0) * 3600.0

            # Degree-weighted demand + stochastic arrival noise + momentum from previous step
            avg_deg = (degree_cache.get(u, 2) + degree_cache.get(v, 2)) / 2.0
            degree_scale = min(avg_deg / 3.5, 1.3)

            # Prior queue spillover effect
            prior_queue = prev_state.get(edge_id, {}).get("queue_length", 0.0)
            queue_lag_factor = min(prior_queue * 0.03, 0.25)

            noise = float(np.random.normal(0.0, 0.08))
            flow_ratio = float(np.clip(t_demand * degree_scale + queue_lag_factor + noise, 0.04, 1.30))
            flow = float(flow_ratio * capacity)

            # BPR speed-flow curve with queue persistence
            sim_tt = float(free_flow_tt * (1.0 + bpr_alpha * (flow_ratio ** bpr_beta)))
            sim_speed = float((length_m / 1000.0) / max(sim_tt / 3600.0, 1e-4))
            sim_speed = float(np.clip(sim_speed, 2.0, speed_kph * 1.05))

            speed_ratio = float(np.clip(sim_speed / max(speed_kph, 1.0), 0.05, 1.05))
            density = float(flow / max(sim_speed, 1.0))
            queue_len = float(max(0.0, (flow_ratio - 0.70) * capacity * 0.025 + 0.6 * prior_queue + np.random.exponential(0.15)))
            wait_time = float(max(0.0, (sim_tt - free_flow_tt) + 0.4 * prior_queue + np.random.exponential(1.2)))
            occupancy = float(np.clip(flow / max(capacity, 1.0), 0.0, 1.35))

            lbl, lbl_name, score = calculate_congestion_labels(
                occupancy=occupancy,
                speed_ratio=speed_ratio,
                queue_length=queue_len,
                wait_time=wait_time,
            )

            step_measurements[edge_id] = {
                "u": int(u),
                "v": int(v),
                "length_m": round(length_m, 2),
                "road_type": road_type,
                "lanes": lanes,
                "speed_kph": round(speed_kph, 1),
                "capacity": int(capacity),
                "flow": round(flow, 2),
                "speed_sim": round(sim_speed, 2),
                "density": round(density, 3),
                "queue_length": round(queue_len, 2),
                "wait_time": round(wait_time, 2),
                "travel_time": round(sim_tt, 2),
                "occupancy": round(occupancy, 4),
                "speed_ratio": round(speed_ratio, 4),
                "widenable": int(widenable),
                "congestion_level": lbl,
                "congestion_label": lbl_name,
                "congestion_score": score,
            }

            prev_state[edge_id] = {
                "flow": flow,
                "speed_sim": sim_speed,
                "occupancy": occupancy,
                "queue_length": queue_len,
            }

        raw_trajectory.append(step_measurements)

    # Now construct the future-prediction samples: Features at time t -> Target at time t+1
    records = []
    for t_idx in range(n_timesteps - 1):
        curr_t = raw_trajectory[t_idx]
        next_t = raw_trajectory[t_idx + 1]
        prev_t = raw_trajectory[t_idx - 1] if t_idx > 0 else curr_t

        for edge_id, curr_data in curr_t.items():
            prev_data = prev_t.get(edge_id, curr_data)
            future_data = next_t.get(edge_id, curr_data)

            # Lagged features (t-1)
            flow_lag1 = prev_data["flow"]
            speed_lag1 = prev_data["speed_sim"]
            occ_lag1 = prev_data["occupancy"]
            queue_lag1 = prev_data["queue_length"]

            # Momentum / rate of change (t vs t-1)
            delta_flow = curr_data["flow"] - flow_lag1
            delta_occ = curr_data["occupancy"] - occ_lag1
            delta_speed = curr_data["speed_sim"] - speed_lag1

            records.append({
                # Metadata & Scenario IDs
                "scenario_id": scenario_idx,
                "time_step": t_idx + 1,
                "scenario_demand": round(float(demand_curve[t_idx]), 3),
                "edge_id": edge_id,
                "u": curr_data["u"],
                "v": curr_data["v"],

                # Static Network Topology
                "length_m": curr_data["length_m"],
                "road_type": curr_data["road_type"],
                "lanes": curr_data["lanes"],
                "speed_kph": curr_data["speed_kph"],
                "capacity": curr_data["capacity"],
                "widenable": curr_data["widenable"],

                # Current Observations at Time t
                "flow_t": curr_data["flow"],
                "speed_sim_t": curr_data["speed_sim"],
                "density_t": curr_data["density"],
                "queue_length_t": curr_data["queue_length"],
                "wait_time_t": curr_data["wait_time"],
                "travel_time_t": curr_data["travel_time"],
                "occupancy_t": curr_data["occupancy"],
                "speed_ratio_t": curr_data["speed_ratio"],

                # Lagged & Momentum Features (t vs t-1)
                "flow_lag1": round(flow_lag1, 2),
                "speed_lag1": round(speed_lag1, 2),
                "occ_lag1": round(occ_lag1, 4),
                "queue_lag1": round(queue_lag1, 2),
                "delta_flow": round(delta_flow, 2),
                "delta_occ": round(delta_occ, 4),
                "delta_speed": round(delta_speed, 2),

                "data_source": "SYNTHETIC_SIMULATION_FUTURE_PREDICTION",

                # Genuine Future Targets at Time t+1
                "future_congestion_level": future_data["congestion_level"],
                "future_congestion_label": future_data["congestion_label"],
                "future_congestion_score": future_data["congestion_score"],
                "future_occupancy": future_data["occupancy"],
                "future_speed_sim": future_data["speed_sim"],
            })

    return records


def generate_dataset(
    num_scenarios: int = 25,
    timesteps_per_scenario: int = 12,
    base_seed: int = 42,
    output_csv: Path | str = DEFAULT_OUTPUT,
) -> pd.DataFrame:
    """
    Generate time-series traffic forecasting dataset across multiple scenarios and time steps.
    """
    out_path = Path(output_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading road network graph for time-series dataset generation...")
    G = load_network_graph()
    total_edges = G.number_of_edges()
    log.info(f"Graph loaded: {G.number_of_nodes()} nodes, {total_edges} edges.")

    # Sample a representative subgraph (1500 edges) across road types
    if total_edges > 2000:
        edge_list = list(G.edges(data=True, keys=True))
        random.seed(base_seed)
        sampled_edges = random.sample(edge_list, min(1500, len(edge_list)))
        H = nx.MultiDiGraph()
        for u, v, k, d in sampled_edges:
            if not H.has_node(u):
                H.add_node(u, **G.nodes[u])
            if not H.has_node(v):
                H.add_node(v, **G.nodes[v])
            H.add_edge(u, v, key=k, **d)
        sim_graph = H
    else:
        sim_graph = G

    log.info(
        f"Simulating {num_scenarios} scenarios with {timesteps_per_scenario} timesteps each "
        f"on {sim_graph.number_of_edges()} edges..."
    )

    # Peak demand distributions across scenarios (from low demand 0.45 to high rush hour 1.25)
    peak_demands = np.linspace(0.40, 1.25, num_scenarios)

    all_records = []
    for idx, peak_d in enumerate(peak_demands):
        seed = base_seed + idx * 23
        scenario_records = simulate_scenario_timeseries(
            sim_graph,
            scenario_idx=idx + 1,
            peak_demand=peak_d,
            n_timesteps=timesteps_per_scenario,
            seed=seed,
        )
        all_records.extend(scenario_records)

    df = pd.DataFrame(all_records)

    # Save to CSV
    df.to_csv(out_path, index=False)
    log.info(f"Time-series future prediction dataset saved to: {out_path}")
    log.info(f"Total records: {len(df):,} rows, {len(df.columns)} columns.")

    class_dist = df["future_congestion_label"].value_counts().to_dict()
    log.info(f"Future Target distribution (future_congestion_level at t+1): {class_dist}")

    # Save metadata summary
    meta = {
        "dataset_type": "SYNTHETIC_SIMULATION_TIME_SERIES_FUTURE_PREDICTION",
        "task": "Predict congestion_level(t+1) given observations up to time t",
        "generated_at": pd.Timestamp.now().isoformat(),
        "num_scenarios": num_scenarios,
        "timesteps_per_scenario": timesteps_per_scenario,
        "total_records": len(df),
        "columns": list(df.columns),
        "target_distribution": class_dist,
        "features_at_t": [
            "length_m", "road_type", "lanes", "speed_kph", "capacity", "widenable",
            "flow_t", "speed_sim_t", "density_t", "queue_length_t", "wait_time_t",
            "travel_time_t", "occupancy_t", "speed_ratio_t",
            "flow_lag1", "speed_lag1", "occ_lag1", "queue_lag1",
            "delta_flow", "delta_occ", "delta_speed",
            "time_step", "scenario_demand"
        ],
        "target_class": "future_congestion_level (0=Low, 1=Moderate, 2=Severe at t+1)",
        "target_continuous": "future_congestion_score (at t+1)",
    }
    meta_path = out_path.parent / "dataset_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2))
    log.info(f"Dataset metadata saved to: {meta_path}")

    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate future traffic prediction simulation dataset.")
    parser.add_argument("--scenarios", type=int, default=25, help="Number of scenarios")
    parser.add_argument("--timesteps", type=int, default=12, help="Number of timesteps per scenario")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUTPUT), help="Output CSV path")
    args = parser.parse_args()

    df = generate_dataset(
        num_scenarios=args.scenarios,
        timesteps_per_scenario=args.timesteps,
        base_seed=args.seed,
        output_csv=args.output,
    )
    print(f"Success: Generated {len(df):,} future prediction records saved to {args.output}")
