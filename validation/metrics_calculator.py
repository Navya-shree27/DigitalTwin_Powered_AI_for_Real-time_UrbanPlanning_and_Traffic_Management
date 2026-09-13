"""
validation/metrics_calculator.py
──────────────────────────────────
Computes KPIs from simulation telemetry.

KPIs computed
─────────────
  avg_travel_time_s           : Mean travel time per edge (seconds)
  avg_wait_time_s             : Mean wait time per vehicle (seconds)
  avg_speed_kph               : Mean simulated speed (km/h)
  p85_travel_time_s           : 85th-percentile travel time
  p85_wait_time_s             : 85th-percentile wait time
  total_flow_veh_h            : Total vehicles / hour across all edges
  throughput_index            : Actual flow as a fraction of total capacity
  congested_edges             : Count of edges with occupancy > 0.75
  congestion_ratio            : congested_edges / total_edges
  emissions_proxy             : Relative fuel/emission index (higher = worse)
                                Estimated from speed using simplified MOVES model:
                                VSP ≈ a×v + b×v³ where a,b are road-type constants.
  total_delay_s               : sum over all edges of (simulated_tt - free_flow_tt)
  efficiency_score            : 0–100 composite score (100 = perfect flow)
  weighted_intersection_delay : Flow-weighted delay (equ.md §1, HCM-based)
  delay_entropy               : Shannon entropy of delay distribution (equ.md §2)
"""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

log = logging.getLogger("metrics_calculator")

# MOVES-simplified emission coefficients (relative units)
EMISSION_A = 0.0015   # rolling resistance + accessory term
EMISSION_B = 0.000004  # aerodynamic drag term (v³ dominant at high speed)


# ── Published equations from equ.md ──────────────────────────────────────────

def weighted_intersection_delay(
    total_delay: list[float],
    flow_rate: list[float],
    lane_count: list[float],
) -> float:
    """
    Flow-weighted intersection delay (equ.md §1).

        d'_I = sum(td_i) / sum(v_i * n_i)

    Source: HCM-based metric used in RL traffic-signal research [web:60].

    Parameters
    ──────────
    total_delay : td_i — total delay per movement / edge (seconds)
    flow_rate   : v_i  — vehicle flow per movement (veh/h)
    lane_count  : n_i  — lane count per movement

    Returns
    ───────
    Delay in seconds per vehicle-lane unit.  0.0 if denominator ≤ 0.
    """
    denominator = sum(v * n for v, n in zip(flow_rate, lane_count))
    if denominator <= 0:
        return 0.0
    return sum(total_delay) / denominator


def delay_entropy(total_delay: list[float]) -> float:
    """
    Shannon entropy of the delay distribution (equ.md §2).

        H_t = -sum(p_i * ln(p_i))   where p_i = td_i / sum(td_j)

    Higher entropy = delay is spread more evenly across movements.
    Lower entropy = delay is concentrated in one or few movements.

    Source: Published RL traffic-signal research [web:60].
    """
    total = sum(d for d in total_delay if d > 0)
    if total <= 0:
        return 0.0
    probs = [d / total for d in total_delay if d > 0]
    return -sum(p * math.log(p) for p in probs)


def compute_metrics(telemetry: dict) -> dict:
    """
    Compute the full KPI set from a telemetry dict (produced by simulation_runner).

    Parameters
    ──────────
    telemetry : dict — standard telemetry schema

    Returns
    ───────
    dict with keys matching the KPI definitions above.
    """
    edges = telemetry.get("edges", [])
    if not edges:
        log.warning("compute_metrics: no edges in telemetry — returning zeros.")
        return _zero_metrics()

    travel_times  = np.array([e.get("travel_time", 0) for e in edges])
    wait_times    = np.array([e.get("wait_time", 0) for e in edges])
    speeds        = np.array([e.get("speed_sim", 0) for e in edges])
    flows         = np.array([e.get("flow", 0) for e in edges])
    capacities    = np.array([e.get("capacity", 1) for e in edges])
    occupancies   = np.array([e.get("occupancy", 0) for e in edges])
    ff_speeds     = np.array([e.get("speed_kph", 40) for e in edges])
    ff_tts        = np.array([
        (e.get("length_m", 100) / 1000) / max(e.get("speed_kph", 40), 1) * 3600
        for e in edges
    ])

    # Emission proxy: area under VSP curve
    emission_values = EMISSION_A * speeds + EMISSION_B * (speeds ** 3)
    emissions_proxy = float(np.mean(emission_values))

    # Noise pollution proxy (in dBA): base level + log10 flow + speed influence
    edge_noises = 45.0 + 10.0 * np.log10(np.maximum(flows, 1)) + 0.2 * speeds
    noise_pollution_db = float(np.mean(edge_noises))

    # Delay
    delays = np.maximum(travel_times - ff_tts, 0)

    # Congestion calculation based on custom formula:
    # score = w1(delay) + w2(queue_length) + w3(stop_count) + w4(travel_time_unreliability)
    w1, w2, w3, w4 = 0.3, 0.3, 0.2, 0.2
    
    # Delays (delay = simulated_tt - free_flow_tt)
    edge_delays = np.maximum(travel_times - ff_tts, 0)
    # Queue lengths
    edge_queues = np.array([e.get("queue_length", 0) for e in edges])
    # Stop count (estimated from wait_time)
    edge_stops = wait_times / 20.0
    # Travel time unreliability (variance proxy based on delays)
    edge_unreliability = edge_delays * 1.2
    
    congestion_scores = (w1 * edge_delays) + (w2 * edge_queues) + (w3 * edge_stops) + (w4 * edge_unreliability)
    
    congested_mask   = (congestion_scores > 8.0) | (occupancies > 0.70)
    congested_count  = int(congested_mask.sum())
    congestion_ratio = congested_count / max(len(edges), 1)

    # Throughput index
    total_flow   = float(flows.sum())
    total_cap    = float(capacities.sum())
    throughput_i = total_flow / max(total_cap, 1)

    # Compute KPIs localized to active flowing edges to prevent skew from empty district roads
    active_mask = flows > 0.05
    if not np.any(active_mask):
        active_mask = np.ones_like(flows, dtype=bool)

    active_speeds = speeds[active_mask]
    active_ff_speeds = ff_speeds[active_mask]
    active_waits = wait_times[active_mask]
    active_travel_times = travel_times[active_mask]

    active_congested = congested_mask[active_mask].sum()
    active_congestion_ratio = active_congested / max(len(active_speeds), 1)

    avg_wait = round(float(np.mean(active_waits)), 2)
    if avg_wait <= 10.0:
        los = "A"
    elif avg_wait <= 20.0:
        los = "B"
    elif avg_wait <= 35.0:
        los = "C"
    elif avg_wait <= 55.0:
        los = "D"
    elif avg_wait <= 80.0:
        los = "E"
    else:
        los = "F"

    eff_score = 100.0 - (active_congestion_ratio * 40.0) - (min(avg_wait, 60.0) / 60.0 * 30.0)
    efficiency_score = round(float(np.clip(eff_score, 0.0, 100.0)), 1)

    # ── equ.md §1 — Weighted Intersection Delay ──────────────────────────────
    edge_wait_list  = [e.get("wait_time", 0) for e in edges]
    edge_flow_list  = [max(e.get("flow", 0), 0) for e in edges]
    edge_lanes_list = [max(e.get("lanes", 1), 1) for e in edges]
    wid = weighted_intersection_delay(edge_wait_list, edge_flow_list, edge_lanes_list)

    # ── equ.md §2 — Delay Entropy ─────────────────────────────────────────────
    d_ent = delay_entropy([e.get("wait_time", 0) for e in edges])

    metrics = {
        "avg_travel_time_s":           round(float(np.mean(active_travel_times)), 2),
        "p85_travel_time_s":           round(float(np.percentile(active_travel_times, 85)), 2),
        "avg_wait_time_s":             avg_wait,
        "p85_wait_time_s":             round(float(np.percentile(wait_times, 85)), 2),
        "avg_speed_kph":               round(float(np.mean(active_speeds)), 2),
        "total_flow_veh_h":            round(total_flow, 0),
        "throughput_index":            round(throughput_i, 4),
        "congested_edges":             int(congested_mask.sum()),
        "total_edges":                 len(edges),
        "congestion_ratio":            round(active_congestion_ratio, 4),
        "total_delay_s":               round(float(delays.sum()), 2),
        "avg_delay_s":                 round(float(delays.mean()), 2),
        "emissions_proxy":             round(emissions_proxy, 4),
        "noise_pollution_db":          round(noise_pollution_db, 2),
        "efficiency_score":            min(100.0, max(0.0, efficiency_score)),
        "level_of_service":            los,
        # Published equations (equ.md)
        "weighted_intersection_delay": round(wid, 4),   # §1
        "delay_entropy":               round(d_ent, 4), # §2
    }
    log.info(
        f"Metrics: speed={metrics['avg_speed_kph']} km/h, "
        f"wait={metrics['avg_wait_time_s']}s, "
        f"congestion={metrics['congestion_ratio']:.1%}, "
        f"noise={metrics['noise_pollution_db']} dBA, "
        f"efficiency={metrics['efficiency_score']}, "
        f"LOS={metrics['level_of_service']}"
    )
    return metrics


def _zero_metrics() -> dict:
    return {
        "avg_travel_time_s": 0, "p85_travel_time_s": 0,
        "avg_wait_time_s": 0,   "p85_wait_time_s": 0,
        "avg_speed_kph": 0,     "total_flow_veh_h": 0,
        "throughput_index": 0,  "congested_edges": 0,
        "total_edges": 0,       "congestion_ratio": 0,
        "total_delay_s": 0,     "avg_delay_s": 0,
        "emissions_proxy": 0,   "noise_pollution_db": 0.0,
        "efficiency_score": 0,  "level_of_service": "A",
        "weighted_intersection_delay": 0.0,  # equ.md §1
        "delay_entropy": 0.0,               # equ.md §2
    }
