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

    approaches = max(2, min(street_count, 6))

    if is_signal:
        cycle_s = green_s + amber_s + red_s
        sat_flow = 1800.0
        flow_per_approach = (total_pce / max(duration_s / 3600.0, 1)) / max(approaches / 2.0, 1.0)
        capacity_per_approach = sat_flow * (green_s / cycle_s)

        x = flow_per_approach / max(capacity_per_approach, 1.0)
        x = min(x, 0.99)

        g_over_c = green_s / cycle_s
        q_pcu_per_s = max(flow_per_approach / 3600.0, 0.0001)

        d1 = 0.5 * cycle_s * (1 - g_over_c) ** 2 / max(1 - x * g_over_c, 0.01)
        d2 = x ** 2 / (2 * q_pcu_per_s * max(1 - x, 0.01))
        delay_s = round(d1 + d2, 2)
        throughput_pce = int(min(total_pce, capacity_per_approach * (approaches / 2.0) * (duration_s / 3600.0)))
        avg_queue = round(q_pcu_per_s * delay_s, 1)
        green_util = round(min(x * 100, 100), 1)
        collision_prob = round(min(0.05 + 0.15 * x, 0.95), 3)
        interpretation = _interpret(delay_s, x, green_util, is_signal=True)
    else:
        # Unsignalized junction
        cycle_s = 0
        hourly_flow = total_pce / max(duration_s / 3600.0, 1)
        major_flow = hourly_flow * 0.65
        minor_flow = hourly_flow * 0.35 / max(approaches - 2, 1)

        # Gap acceptance capacity
        q_maj_s = (major_flow / 2.0) / 3600.0
        cap_minor = max((major_flow / 2.0) * (math.exp(-q_maj_s * 5.0) / max(1.0 - math.exp(-q_maj_s * 3.0), 0.05)), 60.0)

        x = min(minor_flow / cap_minor, 1.5)
        delay_s = round((3600.0 / cap_minor) + (x / max(1.0 - min(x, 0.95), 0.05)) * 4.0, 2)
        avg_queue = round((minor_flow / 3600.0) * delay_s, 1)
        throughput_pce = int(min(total_pce, (major_flow + cap_minor) * (duration_s / 3600.0)))
        green_util = 0.0
        conflict_index = (major_flow * minor_flow) / 150000.0
        collision_prob = round(min(0.15 + conflict_index * 0.35, 0.98), 3)
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
        if conflict_index > 2.0 or delay_s > 45.0:
            return "HAZARDOUS: High crossing conflict and collision risk without signal protection. Installing a traffic signal is strongly warranted."
        if x > 0.8:
            return "WARNING: Minor street vehicles experiencing severe delay waiting for gaps in major flow."
        return "ACCEPTABLE: Unsignalized priority junction handling current traffic volume with adequate gap acceptance."

    if x > 0.9:
        return "CRITICAL: Intersection is over-saturated. Increase green capacity or redistribute traffic."
    if x > 0.75:
        return "WARNING: High saturation. Consider extending green phase or adding a lane."
    if delay_s > 60:
        return "HIGH DELAY: Average wait exceeds 1 minute. Signal timing needs optimization."
    if green_util < 40:
        return "UNDERLOADED: Green phase is barely used. Signal may be removable or replaced with yield control."
    return "ACCEPTABLE: Intersection operating within normal parameters."


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
