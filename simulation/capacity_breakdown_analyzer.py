"""
simulation/capacity_breakdown_analyzer.py
─────────────────────────────────────────
Performs progressive vehicle ramp-up stress testing to determine the
exact Capacity Breakdown Point (Failing Point) for both signalized
and unsignalized junctions in the city network.

Engineering Methodology:
  - Gradually increments vehicle flow (PCE/hr) from free-flow (100 veh/h)
    up to systemic gridlock (6,000 veh/h).
  - For Signalized Intersections:
      * Uses Webster delay + HCM 2010 overflow delay formulations.
      * Failure criteria: Degree of Saturation (v/c) >= 1.0 OR
        Average Delay >= 80.0s (HCM Level of Service F).
  - For Unsignalized / Priority Intersections:
      * Uses HCM Chapter 19/20 Gap Acceptance + Harders capacity model.
      * Models crossing stream conflicts and perpendicular collision probabilities.
      * Failure criteria: Minor capacity exhaustion (v/c >= 1.0) OR
        Delay >= 50.0s OR Conflict Collision Risk >= 4.0.
"""

from __future__ import annotations

import logging
import math
from typing import Any

log = logging.getLogger("capacity_breakdown_analyzer")


def compute_los(delay_s: float, is_signal: bool = True) -> str:
    """Return HCM Level of Service (A-F) based on delay."""
    if is_signal:
        if delay_s <= 10.0:
            return "A"
        elif delay_s <= 20.0:
            return "B"
        elif delay_s <= 35.0:
            return "C"
        elif delay_s <= 55.0:
            return "D"
        elif delay_s <= 80.0:
            return "E"
        else:
            return "F"
    else:
        # Unsignalized LOS thresholds (HCM 2010)
        if delay_s <= 10.0:
            return "A"
        elif delay_s <= 15.0:
            return "B"
        elif delay_s <= 25.0:
            return "C"
        elif delay_s <= 35.0:
            return "D"
        elif delay_s <= 50.0:
            return "E"
        else:
            return "F"


def find_failing_point(
    node_id: str | int,
    is_signal: bool = True,
    street_count: int = 4,
    lanes_per_approach: int = 1,
    green_s: int = 35,
    amber_s: int = 3,
    red_s: int = 35,
    duration_s: int = 300,
    vehicle_mix_ratios: dict[str, float] | None = None,
    current_flow_veh_h: float | None = None,
) -> dict[str, Any]:
    """
    Simulate progressive vehicle ramp-up to determine the exact failure threshold.

    Parameters:
      node_id: Intersection ID
      is_signal: True if signalized, False if priority/unsignalized
      street_count: Number of intersecting approaches (e.g. 3 for T-junction, 4 for crossroad)
      lanes_per_approach: Average lanes per approach leg
      green_s, amber_s, red_s: Signal timing in seconds (if signalized)
      duration_s: Analysis horizon in seconds
      vehicle_mix_ratios: Dict of proportions {'cars': 0.5, 'bikes': 0.25, 'autos': 0.15, 'trucks': 0.05}
      current_flow_veh_h: Actual estimated current flow through node

    Returns:
      Comprehensive failure diagnostics dict with failing volume, failure mode,
      reserve capacity, and progressive breakdown curve.
    """
    if vehicle_mix_ratios is None:
        vehicle_mix_ratios = {"cars": 0.50, "bikes": 0.25, "autos": 0.15, "trucks": 0.05, "buses": 0.05}

    # Normalize mix ratios
    tot_ratio = sum(vehicle_mix_ratios.values()) or 1.0
    ratios = {k: v / tot_ratio for k, v in vehicle_mix_ratios.items()}

    # Average PCE per vehicle in this mix
    pce_per_veh = (
        ratios.get("cars", 0) * 1.0 +
        ratios.get("bikes", 0) * 0.5 +
        ratios.get("autos", 0) * 0.75 +
        ratios.get("trucks", 0) * 2.0 +
        ratios.get("buses", 0) * 2.5
    )

    cycle_s = green_s + amber_s + red_s
    approaches = max(2, min(street_count, 6))
    lanes = max(1, lanes_per_approach)

    # Saturation flow per lane (standard: 1800 pcu/hr)
    sat_flow_lane = 1800.0

    if is_signal:
        green_ratio = green_s / max(cycle_s, 1)
        # Total intersection discharge capacity in PCE/hr
        # Assuming 2 competing phases sharing green time
        capacity_total_pce = sat_flow_lane * lanes * approaches * 0.5 * green_ratio * 2.0
    else:
        # Unsignalized junction capacity under priority control
        # Major flow has free-flow discharge; minor flow restricted by gap acceptance
        capacity_total_pce = sat_flow_lane * lanes * 1.4

    # Flow sweep points from 100 to 6000 veh/h
    test_volumes = [
        100, 200, 300, 450, 600, 750, 900, 1050, 1200, 1350, 1500,
        1700, 1900, 2100, 2300, 2500, 2800, 3100, 3500, 4000, 4500, 5000, 5500, 6000
    ]

    breakdown_curve = []
    failing_vol = None
    failure_mode = None
    failure_delay = None
    failure_queue = None
    failure_los = None

    T_hours = duration_s / 3600.0

    for vol in test_volumes:
        vol_pce = vol * pce_per_veh
        flow_per_approach = vol_pce / approaches

        if is_signal:
            # Capacity per approach for the green phase
            cap_approach = (sat_flow_lane * lanes) * (green_s / max(cycle_s, 1))
            x = flow_per_approach / max(cap_approach, 1.0)
            g_over_c = green_s / max(cycle_s, 1)
            q_pcu_per_s = flow_per_approach / 3600.0

            if x <= 0.95:
                # Webster delay
                d1 = 0.5 * cycle_s * (1.0 - g_over_c) ** 2 / max(1.0 - x * g_over_c, 0.01)
                d2 = (x ** 2) / max(2.0 * q_pcu_per_s * (1.0 - x), 0.001)
                delay_s = d1 + d2
            else:
                # Over-saturation overflow delay (HCM 2010 Akçelik)
                d1 = 0.5 * cycle_s * (1.0 - g_over_c) ** 2 / max(1.0 - 0.95 * g_over_c, 0.01)
                # Overflow incremental delay term
                term = (x - 1.0) + math.sqrt(max((x - 1.0) ** 2 + (8.0 * 0.5 * x) / (cap_approach * T_hours), 0.0))
                d2 = 900.0 * T_hours * term
                delay_s = d1 + d2

            delay_s = round(min(delay_s, 300.0), 1)
            queue_veh = round((flow_per_approach / 3600.0) * delay_s / pce_per_veh, 1)
            los = compute_los(delay_s, is_signal=True)
            collision_prob = round(min(0.05 + 0.15 * min(x, 1.5), 0.95), 3)

            is_failed = (x >= 1.0) or (delay_s >= 80.0)
            fail_reason = "OVER_SATURATION_GREEN_EXHAUSTED" if x >= 1.0 else "EXCESSIVE_CYCLE_DELAY"
            if queue_veh > 25.0 * lanes:
                fail_reason = "SPILLBACK_GRIDLOCK"

        else:
            # Unsignalized Priority Junction Analysis
            # Major approaches = 2, Minor approaches = approaches - 2
            major_flow = vol_pce * 0.65 / 2.0
            minor_flow = vol_pce * 0.35 / max(approaches - 2, 1)

            # Harders / Siegloch gap acceptance critical headway
            tc = 5.0  # critical gap (seconds)
            tf = 3.0  # follow-up time (seconds)

            q_maj_sec = major_flow / 3600.0
            cap_minor = major_flow * (math.exp(-q_maj_sec * tc) / max(1.0 - math.exp(-q_maj_sec * tf), 0.05))
            cap_minor = max(cap_minor, 50.0)

            x = minor_flow / max(cap_minor, 1.0)
            if x < 0.85:
                delay_s = (3600.0 / max(cap_minor, 1.0)) + (x / max(1.0 - x, 0.01)) * 5.0
            else:
                delay_s = (3600.0 / max(cap_minor, 1.0)) + 900.0 * T_hours * (
                    (x - 1.0) + math.sqrt(max((x - 1.0) ** 2 + (4.0 * x) / (cap_minor * T_hours), 0.0))
                ) + 10.0

            delay_s = round(min(delay_s, 300.0), 1)
            queue_veh = round((minor_flow / 3600.0) * delay_s / pce_per_veh, 1)
            los = compute_los(delay_s, is_signal=False)

            # Conflict risk index for unsignalized intersection
            conflict_index = (major_flow * minor_flow) / 200000.0
            collision_prob = round(min(0.12 + conflict_index * 0.4, 0.98), 3)

            is_failed = (x >= 1.0) or (delay_s >= 50.0) or (conflict_index >= 2.5)
            fail_reason = "UNSIGNALIZED_COLLISION_LOCKUP" if conflict_index >= 2.5 else "MINOR_APPROACH_BLOCKAGE"

        point_data = {
            "volume_veh_h": vol,
            "volume_pce_h": round(vol_pce, 1),
            "delay_s": delay_s,
            "queue_veh": queue_veh,
            "saturation_x": round(x, 3),
            "los": los,
            "collision_risk": collision_prob,
            "status": "FAILING" if is_failed else "OPERATIONAL",
        }
        breakdown_curve.append(point_data)

        if is_failed and failing_vol is None:
            failing_vol = vol
            failure_mode = fail_reason
            failure_delay = delay_s
            failure_queue = queue_veh
            failure_los = los

    # Fallback if never exceeded in sweep range
    if failing_vol is None:
        failing_vol = test_volumes[-1]
        failure_mode = "OVER_CAPACITY_LIMIT"
        failure_delay = breakdown_curve[-1]["delay_s"]
        failure_queue = breakdown_curve[-1]["queue_veh"]
        failure_los = "F"

    # Current load and reserve capacity analysis
    est_current = current_flow_veh_h if current_flow_veh_h and current_flow_veh_h > 0 else 650.0
    load_pct = round((est_current / max(failing_vol, 1)) * 100.0, 1)
    reserve_veh_h = max(0, failing_vol - int(est_current))

    # Engineering recommendations based on failure mode
    if is_signal:
        if "OVER_SATURATION" in failure_mode:
            rec = f"Extend primary green phase from {green_s}s to {green_s + 12}s or add 1 approach lane to lift failing point by ~450 veh/h."
        elif "SPILLBACK" in failure_mode:
            rec = "Implement upstream metering and lengthen turning storage bays to eliminate spillback blockage."
        else:
            rec = "Optimize cycle length to 90s Webster optimal timing to reduce queuing delay."
    else:
        if "COLLISION" in failure_mode or "BLOCKAGE" in failure_mode:
            rec = f"WARRANTS TRAFFIC SIGNAL: Intersection fails at only {failing_vol} veh/h without signal control. Installing a 2-phase signal will raise failing point to ~{int(failing_vol * 1.7)} veh/h."
        else:
            rec = "Convert to compact mini-roundabout or install active stop signs to manage crossing conflict points."

    return {
        "node_id": str(node_id),
        "is_signal": is_signal,
        "street_count": street_count,
        "lanes_per_approach": lanes,
        "failing_point_veh_h": failing_vol,
        "failing_point_veh_min": round(failing_vol / 60.0, 1),
        "estimated_current_flow_veh_h": round(est_current, 0),
        "current_load_pct": load_pct,
        "reserve_capacity_veh_h": reserve_veh_h,
        "failure_mode": failure_mode,
        "failure_delay_s": failure_delay,
        "failure_queue_veh": failure_queue,
        "failure_los": failure_los,
        "recommendation": rec,
        "breakdown_curve": breakdown_curve,
    }


def analyze_citywide_failing_points(
    scenario_id: int,
    G: Any = None,
    telemetry: dict | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Perform a citywide scan across all signals and major junctions to identify
    each junction's failing point and rank the city's most vulnerable intersections.
    """
    if G is None:
        from simulation.simulation_runner import load_graph
        G = load_graph(scenario_id)

    # Get edge flows mapped to nodes
    node_flows = {}
    if telemetry and "edges" in telemetry:
        for e in telemetry["edges"]:
            v = e.get("v")
            if v is not None:
                node_flows[v] = node_flows.get(v, 0.0) + e.get("flow", 0.0)

    results = []
    signal_count = 0
    unsignal_count = 0

    for node_id, data in G.nodes(data=True):
        sc = int(data.get("street_count", G.degree(node_id)))
        is_signal = data.get("highway") == "traffic_signals"

        # Scan signals and any junctions with >= 3 approaches
        if not is_signal and sc < 3:
            continue

        lanes = 1
        for u, v, k, edata in G.edges(node_id, data=True, keys=True):
            elanes = edata.get("lanes", 1)
            if isinstance(elanes, list):
                elanes = elanes[0]
            try:
                lanes = max(lanes, int(elanes))
            except (ValueError, TypeError):
                pass

        cur_flow = node_flows.get(node_id, node_flows.get(int(node_id) if str(node_id).isdigit() else None, 450.0))

        fp = find_failing_point(
            node_id=node_id,
            is_signal=is_signal,
            street_count=sc,
            lanes_per_approach=lanes,
            current_flow_veh_h=cur_flow,
        )

        fp["lat"] = float(data.get("y", 0.0))
        fp["lon"] = float(data.get("x", 0.0))
        fp["designation"] = data.get("designation") or data.get("name") or ("Signal" if is_signal else "Junction")

        results.append(fp)
        if is_signal:
            signal_count += 1
        else:
            unsignal_count += 1

    # Sort by vulnerability (highest current_load_pct / lowest reserve capacity first)
    results.sort(key=lambda x: x["current_load_pct"], reverse=True)

    vulnerable_signals = [r for r in results if r["is_signal"] and r["current_load_pct"] >= 70.0]
    vulnerable_unsignaled = [r for r in results if not r["is_signal"] and r["current_load_pct"] >= 65.0]

    return {
        "scenario_id": scenario_id,
        "total_analyzed": len(results),
        "signals_analyzed": signal_count,
        "unsignalized_analyzed": unsignal_count,
        "most_vulnerable_intersections": results[:limit],
        "critical_signals_near_failure": vulnerable_signals[:10],
        "high_risk_unsignalized_crossings": vulnerable_unsignaled[:10],
    }
