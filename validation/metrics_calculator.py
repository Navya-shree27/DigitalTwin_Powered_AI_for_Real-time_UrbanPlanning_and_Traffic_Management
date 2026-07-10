"""
validation/metrics_calculator.py
──────────────────────────────────
Computes KPIs from simulation telemetry.

KPIs computed
─────────────
  avg_travel_time_s    : Mean travel time per edge (seconds)
  avg_wait_time_s      : Mean wait time per vehicle (seconds)
  avg_speed_kph        : Mean simulated speed (km/h)
  p85_travel_time_s    : 85th-percentile travel time
  p85_wait_time_s      : 85th-percentile wait time
  total_flow_veh_h     : Total vehicles / hour across all edges
  throughput_index     : Actual flow as a fraction of total capacity
  congested_edges      : Count of edges with occupancy > 0.75
  congestion_ratio     : congested_edges / total_edges
  emissions_proxy      : Relative fuel/emission index (higher = worse)
                         Estimated from speed using simplified MOVES model:
                         VSP ≈ a×v + b×v³ where a,b are road-type constants.
  total_delay_s        : sum over all edges of (simulated_tt - free_flow_tt)
  efficiency_score     : 0–100 composite score (100 = perfect flow)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger("metrics_calculator")

# MOVES-simplified emission coefficients (relative units)
EMISSION_A = 0.0015   # rolling resistance + accessory term
EMISSION_B = 0.000004  # aerodynamic drag term (v³ dominant at high speed)


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

    # Efficiency score (0–100): weights speed, congestion, wait time
    speed_score      = float(np.mean(speeds / np.maximum(ff_speeds, 1))) * 100
    congestion_score = (1 - congestion_ratio) * 100
    wait_score       = max(0, 100 - float(np.mean(wait_times)) / 60 * 100)
    efficiency_score = round(0.4 * speed_score + 0.4 * congestion_score + 0.2 * wait_score, 1)

    metrics = {
        "avg_travel_time_s":   round(float(np.mean(travel_times)), 2),
        "p85_travel_time_s":   round(float(np.percentile(travel_times, 85)), 2),
        "avg_wait_time_s":     round(float(np.mean(wait_times)), 2),
        "p85_wait_time_s":     round(float(np.percentile(wait_times, 85)), 2),
        "avg_speed_kph":       round(float(np.mean(speeds)), 2),
        "total_flow_veh_h":    round(total_flow, 0),
        "throughput_index":    round(throughput_i, 4),
        "congested_edges":     congested_count,
        "total_edges":         len(edges),
        "congestion_ratio":    round(congestion_ratio, 4),
        "total_delay_s":       round(float(delays.sum()), 2),
        "avg_delay_s":         round(float(delays.mean()), 2),
        "emissions_proxy":     round(emissions_proxy, 4),
        "noise_pollution_db":  round(noise_pollution_db, 1),
        "efficiency_score":    min(100.0, max(0.0, efficiency_score)),
    }
    log.info(
        f"Metrics: speed={metrics['avg_speed_kph']} km/h, "
        f"wait={metrics['avg_wait_time_s']}s, "
        f"congestion={metrics['congestion_ratio']:.1%}, "
        f"noise={metrics['noise_pollution_db']} dBA, "
        f"efficiency={metrics['efficiency_score']}"
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
        "emissions_proxy": 0,   "noise_pollution_db": 0.0, "efficiency_score": 0,
    }
