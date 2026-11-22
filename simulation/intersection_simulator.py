"""
simulation/intersection_simulator.py
─────────────────────────────────────
Single-intersection SUMO micro-simulation for per-signal testing.
Generates a minimal SUMO network, runs TraCI, returns metrics.
"""
from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("intersection_simulator")

SUMO_HOME = Path(os.environ.get("SUMO_HOME", r"C:\Program Files (x86)\Eclipse\Sumo"))
SUMO_BIN  = SUMO_HOME / "bin" / "sumo.exe"
NETGEN    = SUMO_HOME / "bin" / "netgenerate.exe"


def _sumo_available() -> bool:
    return SUMO_BIN.exists() and NETGEN.exists()


def simulate_intersection(
    node_id: str | int,
    vehicle_mix: dict[str, int],   # e.g. {"cars": 50, "bikes": 20, "autos": 10, "trucks": 5}
    green_s: int = 35,
    amber_s: int = 3,
    red_s:   int = 35,
    duration_s: int = 300,
    lat: float = 0.0,
    lon: float = 0.0,
    is_signal: bool = True,
    street_count: int = 4,
) -> dict[str, Any]:
    """
    Run a micro-simulation for a single intersection and return metrics.
    Supports both signalized and unsignalized (priority/uncontrolled) junctions.
    Falls back to analytic model if SUMO is unavailable.
    """
    from simulation.capacity_breakdown_analyzer import find_failing_point

    if is_signal and _sumo_available():
        try:
            res = _run_sumo_sim(node_id, vehicle_mix, green_s, amber_s, red_s, duration_s)
            res["failing_point"] = find_failing_point(
                node_id=node_id,
                is_signal=True,
                street_count=street_count,
                green_s=green_s,
                amber_s=amber_s,
                red_s=red_s,
                duration_s=duration_s,
            )
            return res
        except Exception as e:
            log.warning(f"SUMO sim failed ({e}), falling back to analytic model")

    res = _analytic_model(
        node_id=node_id,
        vehicle_mix=vehicle_mix,
        green_s=green_s,
        amber_s=amber_s,
        red_s=red_s,
        duration_s=duration_s,
        is_signal=is_signal,
        street_count=street_count,
    )
    res["failing_point"] = find_failing_point(
        node_id=node_id,
        is_signal=is_signal,
        street_count=street_count,
        green_s=green_s,
        amber_s=amber_s,
        red_s=red_s,
        duration_s=duration_s,
    )
    return res


# ── Analytic model (Signalized Webster & Unsignalized Priority Gap Acceptance) ─

def _analytic_model(
    node_id: str | int,
    vehicle_mix: dict[str, int],
    green_s: int,
    amber_s: int,
    red_s: int,
    duration_s: int,
    is_signal: bool = True,
    street_count: int = 4,
) -> dict[str, Any]:
    """
    Analytic model for both signalized (Webster) and unsignalized (HCM Gap Acceptance) intersections.
    """
    cars   = vehicle_mix.get("cars", 0)
    bikes  = vehicle_mix.get("bikes", 0)
    autos  = vehicle_mix.get("autos", 0)   # auto-rickshaws
    trucks = vehicle_mix.get("trucks", 0)
    buses  = vehicle_mix.get("buses", 0)

    # PCE (Passenger Car Equivalents)
    total_pce = cars + (bikes * 0.5) + (autos * 0.75) + (trucks * 2.0) + (buses * 2.5)
    total_veh = cars + bikes + autos + trucks + buses

    duration_hours = max(float(duration_s), 10.0) / 3600.0
    hourly_flow = total_pce / duration_hours

    approaches = max(2, min(street_count, 6))

    if is_signal:
        cycle_s = max(green_s + amber_s + red_s, 10)
        sat_flow = 1800.0
        # Approach legs share cycle capacity
        flow_per_approach = hourly_flow / float(approaches)
        capacity_per_approach = sat_flow * (green_s / float(cycle_s))

        x = flow_per_approach / max(capacity_per_approach, 1.0)
        g_over_c = green_s / float(cycle_s)
        q_pcu_per_s = max(flow_per_approach / 3600.0, 0.0001)

        if x <= 0.95:
            d1 = 0.5 * cycle_s * (1 - g_over_c) ** 2 / max(1 - x * g_over_c, 0.01)
            d2 = x ** 2 / (2 * q_pcu_per_s * max(1 - x, 0.01))
            delay_s = round(d1 + d2, 2)
        else:
            # Over-saturation overflow delay (HCM 2010 Akçelik)
            d1 = 0.5 * cycle_s * (1 - g_over_c) ** 2 / max(1 - 0.95 * g_over_c, 0.01)
            term = (x - 1.0) + math.sqrt(max((x - 1.0) ** 2 + (8.0 * 0.5 * x) / (capacity_per_approach * duration_hours), 0.0))
            d2 = 900.0 * duration_hours * term
            delay_s = round(min(d1 + d2, 300.0), 2)

        total_capacity_hourly = capacity_per_approach * approaches
        throughput_pce = int(min(total_pce, total_capacity_hourly * duration_hours))
        avg_queue = round(min(q_pcu_per_s * delay_s, total_pce / approaches), 1)
        green_util = round(min(x * 100, 100), 1)
        collision_prob = round(min(0.05 + 0.15 * min(x, 2.0), 0.95), 3)
        interpretation = _interpret(delay_s, x, green_util, is_signal=True)
    else:
        # Unsignalized Priority Intersection (HCM 2010 Chapter 19/20 Gap Acceptance)
        cycle_s = 0
        major_approaches = 2
        minor_approaches = max(approaches - major_approaches, 1)

        major_flow_total = hourly_flow * 0.65
        minor_flow_total = hourly_flow * 0.35
        major_flow_per_app = major_flow_total / major_approaches
        minor_flow_per_app = minor_flow_total / minor_approaches

        # Minor street vehicles must yield and find critical headway gaps (tc = 5.0s, tf = 3.0s) in major stream
        q_maj_s = major_flow_per_app / 3600.0
        tc = 5.0  # critical gap (seconds)
        tf = 3.0  # follow-up gap (seconds)

        if q_maj_s > 0:
            p_gap = math.exp(-q_maj_s * tc)
            p_follow = max(1.0 - math.exp(-q_maj_s * tf), 0.04)
            cap_minor_per_app = max(major_flow_per_app * (p_gap / p_follow), 50.0)
        else:
            cap_minor_per_app = 1200.0

        x = minor_flow_per_app / max(cap_minor_per_app, 1.0)

        if x <= 0.95:
            # Under-capacity queuing delay
            delay_s = round((3600.0 / cap_minor_per_app) + (x / max(1.0 - x, 0.05)) * 4.0, 2)
        else:
            # Severe over-saturation accumulation delay
            base_d = 3600.0 / cap_minor_per_app
            term = (x - 1.0) + math.sqrt(max((x - 1.0) ** 2 + (8.0 * x) / (cap_minor_per_app * duration_hours), 0.0))
            overflow_d = 900.0 * duration_hours * term
            delay_s = round(min(base_d + overflow_d, 300.0), 2)

        # Queue accumulation
        if x > 1.0:
            accumulated_queue = (minor_flow_per_app - cap_minor_per_app) * duration_hours
            avg_queue = round(max((minor_flow_per_app / 3600.0) * delay_s, accumulated_queue / 2.0), 1)
        else:
            avg_queue = round((minor_flow_per_app / 3600.0) * delay_s, 1)

        # Discharged throughput in duration window
        major_capacity_total = 1800.0 * major_approaches
        major_discharged = min(major_flow_total, major_capacity_total) * duration_hours
        minor_discharged = min(minor_flow_total, cap_minor_per_app * minor_approaches) * duration_hours
        throughput_pce = int(min(total_pce, major_discharged + minor_discharged))

        green_util = 0.0
        conflict_index = (major_flow_total * minor_flow_total) / 150000.0
        collision_prob = round(min(0.15 + conflict_index * 0.15 + min(x * 0.25, 0.55), 0.98), 3)
        interpretation = _interpret(delay_s, x, green_util, is_signal=False, conflict_index=conflict_index)

    emissions = round(total_pce * delay_s * 0.03, 2)

    return {
        "node_id": str(node_id),
        "is_signal": is_signal,
        "street_count": approaches,
        "engine": "analytic_webster" if is_signal else "analytic_unsignalized_gap_acceptance",
        "vehicle_mix": vehicle_mix,
        "total_vehicles": total_veh,
        "total_pce": round(total_pce, 1),
        "signal_config": {
            "green_s": green_s,
            "amber_s": amber_s,
            "red_s": red_s,
            "cycle_s": cycle_s,
        } if is_signal else None,
        "metrics": {
            "avg_wait_time_s":     delay_s,
            "avg_queue_length":    avg_queue,
            "throughput_veh":      throughput_pce,
            "green_utilization_pct": green_util,
            "degree_of_saturation": round(x, 3),
            "emissions_proxy":      emissions,
            "collision_risk_score": collision_prob,
        },
        "interpretation": interpretation,
    }


def _interpret(delay_s: float, x: float, green_util: float, is_signal: bool = True, conflict_index: float = 0.0) -> str:
    if not is_signal:
        if x >= 1.0 or delay_s >= 50.0 or conflict_index > 2.0:
            return f"CRITICAL BREAKDOWN: Severe over-saturation (v/c = {x:.2f}). Minor approaches cannot find safe crossing gaps in the heavy major stream. Installing a multi-phase traffic signal is urgently required to prevent severe collisions and gridlock."
        if x > 0.75 or delay_s > 30.0:
            return f"WARNING: High crossing conflict (v/c = {x:.2f}). Minor street vehicles experiencing extended delays waiting for gaps. Signalization recommended."
        return f"ACCEPTABLE: Unsignalized priority junction operating within capacity (v/c = {x:.2f}) with adequate gap acceptance."

    if x >= 1.0 or delay_s >= 80.0:
        return f"CRITICAL BREAKDOWN: Intersection is over-saturated (v/c = {x:.2f}, delay {delay_s:.1f}s). Demand exceeds approach discharge capacity. Increase cycle length, add green time, or provide additional turning lanes."
    if x > 0.8:
        return f"WARNING: High saturation (v/c = {x:.2f}). Approaching capacity limit. Consider extending green phase or reallocating cycle splits."
    if delay_s > 60:
        return f"HIGH DELAY: Average wait exceeds 1 minute ({delay_s:.1f}s). Signal phase timing requires re-coordination."
    if green_util < 35:
        return f"UNDERLOADED: Green phase is underutilized ({green_util:.0f}%). Signal may be removable or replaced with actuated/priority control."
    return f"ACCEPTABLE: Intersection operating within normal parameters (v/c = {x:.2f}, wait {delay_s:.1f}s)."


# ── SUMO-based simulation ─────────────────────────────────────────────────────

def _run_sumo_sim(
    node_id: str | int,
    vehicle_mix: dict[str, int],
    green_s: int,
    amber_s: int,
    red_s: int,
    duration_s: int,
) -> dict[str, Any]:
    """Generate minimal SUMO files and run micro-simulation via subprocess."""
    with tempfile.TemporaryDirectory(prefix="dt_intersim_") as tmpdir:
        tmp = Path(tmpdir)

        # 1. Generate minimal star network: 1 central node + 4 approach legs
        nod_xml = tmp / "inter.nod.xml"
        edg_xml = tmp / "inter.edg.xml"
        net_xml = tmp / "inter.net.xml"
        rou_xml = tmp / "inter.rou.xml"
        cfg_xml = tmp / "inter.sumocfg"
        out_xml = tmp / "output.xml"

        ARM_LEN = 150  # metres per arm

        nod_xml.write_text(
            '<?xml version="1.0"?>\n<nodes>\n'
            f'  <node id="C" x="0" y="0" type="traffic_light"/>\n'
            f'  <node id="N" x="0"  y="{ARM_LEN}" type="priority"/>\n'
            f'  <node id="S" x="0"  y="-{ARM_LEN}" type="priority"/>\n'
            f'  <node id="E" x="{ARM_LEN}"  y="0" type="priority"/>\n'
            f'  <node id="W" x="-{ARM_LEN}" y="0" type="priority"/>\n'
            '</nodes>\n'
        )

        edges = [("N", "C"), ("S", "C"), ("E", "C"), ("W", "C"),
                 ("C", "N"), ("C", "S"), ("C", "E"), ("C", "W")]
        edg_lines = '<?xml version="1.0"?>\n<edges>\n'
        for frm, to in edges:
            edg_lines += f'  <edge id="{frm}{to}" from="{frm}" to="{to}" numLanes="1" speed="13.9"/>\n'
        edg_lines += '</edges>\n'
        edg_xml.write_text(edg_lines)

        # Build network
        subprocess.run([
            str(NETGEN),
            "--node-files", str(nod_xml),
            "--edge-files", str(edg_xml),
            "--output-file", str(net_xml),
            "--no-turnarounds",
        ], capture_output=True, timeout=30, check=True)

        # 2. Build routes XML
        cars   = vehicle_mix.get("cars", 0)
        bikes  = vehicle_mix.get("bikes", 0)
        autos  = vehicle_mix.get("autos", 0)
        trucks = vehicle_mix.get("trucks", 0)
        buses  = vehicle_mix.get("buses", 0)

        rou_lines = '<?xml version="1.0"?>\n<routes>\n'
        rou_lines += '  <vType id="car" vClass="passenger" maxSpeed="13.9" accel="2.6" decel="4.5" sigma="0.5"/>\n'
        rou_lines += '  <vType id="bike" vClass="moped" maxSpeed="8.3" accel="1.5" decel="3.0" sigma="0.7" width="0.9"/>\n'
        rou_lines += '  <vType id="auto" vClass="moped" maxSpeed="11.1" accel="2.0" decel="3.5" sigma="0.6" width="1.2" color="1,0.5,0"/>\n'
        rou_lines += '  <vType id="truck" vClass="truck" maxSpeed="11.1" accel="1.2" decel="3.0" sigma="0.3" color="0.5,0.5,0.5"/>\n'
        rou_lines += '  <vType id="bus" vClass="bus" maxSpeed="11.1" accel="1.0" decel="3.5" sigma="0.3" color="0,0,1"/>\n'

        # Route: N→S, E→W in both directions
        for dir_pair in [("N", "S"), ("S", "N"), ("E", "W"), ("W", "E")]:
            rou_lines += f'  <route id="rt_{dir_pair[0]}{dir_pair[1]}" edges="{dir_pair[0]}C C{dir_pair[1]}"/>\n'

        def add_veh_flow(vtype, count, route_id, depart_start, depart_end):
            if count <= 0:
                return ""
            period = max(1, (depart_end - depart_start) / max(count, 1))
            line = ""
            for i in range(count):
                dep = round(depart_start + i * period, 1)
                line += f'  <vehicle id="{vtype}_{route_id}_{i}" type="{vtype}" route="{route_id}" depart="{dep}"/>\n'
            return line

        # Distribute vehicles across all 4 approach routes
        total_veh = cars + bikes + autos + trucks + buses
        routes_list = ["rtNS", "rtSN", "rtEW", "rtWE"]
        for i, rt in enumerate([("N","S"), ("S","N"), ("E","W"), ("W","E")]):
            rt_id = f"rt_{rt[0]}{rt[1]}"
            share = max(1, total_veh // 4)
            rou_lines += add_veh_flow("car",   max(1, cars//4),   rt_id, 0, duration_s * 0.8)
            if bikes:  rou_lines += add_veh_flow("bike",  bikes//4,  rt_id, 0, duration_s * 0.8)
            if autos:  rou_lines += add_veh_flow("auto",  autos//4,  rt_id, 0, duration_s * 0.8)
            if trucks: rou_lines += add_veh_flow("truck", trucks//4, rt_id, 0, duration_s * 0.8)
            if buses:  rou_lines += add_veh_flow("bus",   buses//4,  rt_id, 0, duration_s * 0.8)

        rou_lines += '</routes>\n'
        rou_xml.write_text(rou_lines)

        # 3. SUMO config
        cfg_xml.write_text(
            '<?xml version="1.0"?>\n<configuration>\n'
            f'  <input><net-file value="{net_xml}"/><route-files value="{rou_xml}"/></input>\n'
            f'  <time><begin value="0"/><end value="{duration_s}"/></time>\n'
            f'  <output><summary-output value="{out_xml}"/></output>\n'
            '</configuration>\n'
        )

        # 4. Run SUMO (no GUI)
        result = subprocess.run([
            str(SUMO_BIN), "-c", str(cfg_xml),
            "--no-warnings", "--xml-validation", "never",
        ], capture_output=True, timeout=120, text=True)

        # 5. Parse output XML for metrics
        avg_wait = 0.0
        throughput = 0
        if out_xml.exists():
            import xml.etree.ElementTree as ET
            try:
                tree = ET.parse(out_xml)
                for step in tree.getroot().iter("step"):
                    avg_wait += float(step.get("meanWaitingTime", 0))
                    throughput = max(throughput, int(step.get("arrived", 0)))
                steps = len(list(tree.getroot().iter("step")))
                avg_wait = round(avg_wait / max(steps, 1), 2)
            except Exception as xe:
                log.warning(f"Error parsing SUMO output: {xe}")

        cycle_s = green_s + amber_s + red_s
        return {
            "node_id": str(node_id),
            "engine": "sumo",
            "vehicle_mix": vehicle_mix,
            "total_vehicles": total_veh,
            "signal_config": {"green_s": green_s, "amber_s": amber_s, "red_s": red_s, "cycle_s": cycle_s},
            "metrics": {
                "avg_wait_time_s": avg_wait,
                "throughput_veh": throughput,
                "green_utilization_pct": min(100, round((total_veh / max(duration_s / cycle_s * 4, 1)) * 100, 1)),
                "degree_of_saturation": round(avg_wait / max(cycle_s, 1), 3),
                "emissions_proxy": round(avg_wait * total_veh * 0.03, 2),
            },
            "interpretation": _interpret(avg_wait, avg_wait / max(cycle_s, 1), 50),
        }
