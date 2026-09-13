"""
ai/proposal_generator/capacity_analyzer.py
───────────────────────────────────────────────────────────
Signal Capacity & N-Vehicle What-If Outcome Analyzer

Implements IRC:106-2010 and HCM (Highway Capacity Manual) standards
to compute real-world maximum throughput capacity, saturation degree,
Webster's delay, queue backlog, Level of Service (LOS Grade A-F),
and actionable municipal engineering recommendations.

Key Equations:
  Saturation Flow: S = 1800 × lanes × PHF (PCU/hr per approach)
  Effective Green: g = green_s (simplified single-phase)
  Cycle Length: C = green_s + amber_s + red_s
  Capacity: c = S × (g / C)           [PCU/hr per approach]
  Volume-Capacity Ratio: X = flow / c
  Webster Delay: d = [C(1 - g/C)² / 2(1-X·g/C)] + [X² / (2q(1-X))]
  Queue Backlog: L = X × c × (vehicle_length + spacing) / 3600
"""

from __future__ import annotations

SATURATION_FLOW_BASE = 1800   # PCU/hr per lane (IRC standard for urban signalized)
VEHICLE_LENGTH_M     = 4.5    # Average car length in India (m)
VEHICLE_SPACING_M    = 1.5    # Jam spacing buffer (m)
VEHICLE_TOTAL_M      = VEHICLE_LENGTH_M + VEHICLE_SPACING_M  # = 6m per PCU

# Level of Service thresholds (HCM v6 — Table 19-2, urban intersection)
LOS_THRESHOLDS = [
    ("A", 10,   "#22c55e", "Excellent flow — minimal delay."),
    ("B", 20,   "#84cc16", "Good flow — acceptable minor delay."),
    ("C", 35,   "#eab308", "Fair flow — drivers notice delay."),
    ("D", 55,   "#f97316", "Poor flow — significant delay, noticeable queuing."),
    ("E", 80,   "#ef4444", "Critical — operating near capacity, heavy queues."),
    ("F", 9999, "#7f1d1d", "Breakdown — demand exceeds capacity, gridlock risk."),
]

# Municipal capacity-based recommendations
def _municipal_recommendation(x_vc: float, capacity: float, lanes: int, green_s: int, cycle_s: int) -> list[str]:
    recs = []
    if x_vc < 0.7:
        recs.append("✅ This intersection operates well within capacity. No immediate infrastructure change required.")
    elif x_vc < 0.85:
        recs.append("⚠️ Intersection is in high-utilization range. Consider extending green phase by 5–10 seconds.")
    elif x_vc < 1.0:
        recs.append("🚨 Approaching saturation. Strongly recommend adding a dedicated right-turn slip lane (IRC:86-1983 §7.4).")
        if green_s < 50:
            recs.append(f"⏱️ Increase green phase from {green_s}s to {min(green_s + 15, 60)}s using Webster's optimal cycle.")
        if cycle_s > 90:
            recs.append("🔄 Consider splitting this junction into two separate signal phases to reduce average cycle length.")
    else:
        recs.append("🚨 CRITICAL: Volume exceeds capacity. Infrastructure upgrade required.")
        if lanes < 3:
            recs.append(f"🛣️ Road Widening: Expand from {lanes} to {lanes + 1} lanes per approach (IRC:86 §6.2).")
        recs.append("🛤️ Grade Separation: Evaluate flyover or underpass feasibility for this corridor.")
        recs.append("🔀 Route Diversion: Immediately implement alternate routing to redistribute demand.")

    if lanes == 1 and capacity > 0 and (1800 / capacity) > 0.5:
        recs.append("🏗️ Consider adding a second approach lane. Single-lane capacity is severely limiting throughput.")

    return recs


def analyze_capacity(
    flow: float,         # Arriving vehicles per hour (veh/h)
    green_s: int,        # Green phase duration (seconds)
    amber_s: int,        # Amber/clearance phase (seconds)
    red_s: int,          # Red phase duration (seconds)
    lanes: int,          # Number of approach lanes at this signal
    phf: float = 0.92,   # Peak Hour Factor (0.85-0.95, IRC default 0.92)
) -> dict:
    """
    Compute signal capacity, saturation, delay, queue, LOS, and recommendations.
    Returns a detailed analysis dict ready for serialization.
    """
    cycle_s = green_s + amber_s + red_s

    # Saturation flow (IRC:106 calibrated for Indian mixed traffic)
    sat_flow = SATURATION_FLOW_BASE * lanes * phf

    # Approach capacity (PCU/hr)
    g_over_c = green_s / cycle_s if cycle_s > 0 else 0
    capacity = sat_flow * g_over_c

    # Adjusted demand flow (account for PHF)
    demand = flow / phf if phf > 0 else flow

    # Volume-to-Capacity ratio
    x_vc = demand / capacity if capacity > 0 else 99.0
    x_capped = min(x_vc, 1.2)   # Cap for formula stability

    # Webster's Control Delay (s/vehicle) — HCM Equation 19-15
    try:
        term1_denom = 1 - (x_capped * g_over_c)
        term1 = (cycle_s * (1 - g_over_c) ** 2) / (2 * term1_denom) if abs(term1_denom) > 0.001 else 999
        q_flow = demand / 3600  # vehicles per second
        term2_denom = 2 * q_flow * (1 - x_capped)
        term2 = (x_capped ** 2) / term2_denom if abs(term2_denom) > 0.001 and q_flow > 0 else 0
        delay_s = max(0, term1 + term2)
    except Exception:
        delay_s = 999

    # Queue backlog — number of queued vehicles (at jam density)
    queue_vehicles = max(0, round((x_vc - 1) * capacity / 6 + (flow * red_s / 3600), 1)) if x_vc > 0.5 else round(flow * red_s / 3600 * 0.4, 1)
    queue_m = round(queue_vehicles * VEHICLE_TOTAL_M, 1)

    # Level of Service grade
    los_grade = "F"
    los_color = "#7f1d1d"
    los_description = "Breakdown — demand exceeds capacity."
    for grade, threshold, color, desc in LOS_THRESHOLDS:
        if delay_s <= threshold:
            los_grade = grade
            los_color = color
            los_description = desc
            break

    # Throughput — actual vehicles that can flow through
    throughput = min(flow, capacity)

    # Vehicles stuck / unable to clear each cycle
    blocked_per_hour = max(0, flow - capacity)

    # Max flow before LOS degrades to F (theoretical)
    max_flow_before_f = capacity * 0.95   # HCM recommends keeping X < 0.95

    recs = _municipal_recommendation(x_vc, capacity, lanes, green_s, cycle_s)

    return {
        "input": {
            "flow_veh_hr": round(flow, 1),
            "green_s": green_s,
            "amber_s": amber_s,
            "red_s": red_s,
            "cycle_s": cycle_s,
            "lanes": lanes,
            "phf": phf,
        },
        "capacity": {
            "saturation_flow_pcu_hr": round(sat_flow, 0),
            "approach_capacity_pcu_hr": round(capacity, 0),
            "max_safe_flow_veh_hr": round(max_flow_before_f, 0),
            "g_over_c_ratio": round(g_over_c, 3),
        },
        "performance": {
            "x_vc": round(x_vc, 3),
            "delay_s_per_vehicle": round(delay_s, 1),
            "queue_vehicles": round(queue_vehicles, 1),
            "queue_length_m": queue_m,
            "throughput_veh_hr": round(throughput, 0),
            "blocked_veh_hr": round(blocked_per_hour, 0),
        },
        "los": {
            "grade": los_grade,
            "color": los_color,
            "description": los_description,
            "delay_s": round(delay_s, 1),
        },
        "recommendations": recs,
        "warning": x_vc > 1.0,
        "critical": x_vc >= 1.2,
    }
