"""
simulation/traci_interface.py
──────────────────────────────
Live read/write interface into a running SUMO simulation via TraCI.

Phase A behaviour
─────────────────
If SUMO/TraCI is not installed (import fails), this module silently falls back
to returning a "not available" payload so the rest of the system can still run.
Full TraCI wiring is planned for Phase B once SUMO is confirmed installed.

Usage (Phase B+)
────────────────
    from simulation.traci_interface import SUMOTraCIInterface
    iface = SUMOTraCIInterface(G, duration_s=3600, seed=42)
    result = iface.run()
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger("traci_interface")

ROOT = Path(__file__).resolve().parent.parent
SUMO_CFG = ROOT / "simulation" / "sumo_config" / "simulation.sumocfg"

# ── Try importing TraCI ───────────────────────────────────────────────────────
try:
    import traci  # type: ignore
    TRACI_AVAILABLE = True
    log.info("TraCI imported successfully — SUMO integration is available.")
except ImportError:
    TRACI_AVAILABLE = False
    log.warning(
        "TraCI not available (SUMO not installed). "
        "Using synthetic simulation fallback."
    )


class SUMOTraCIInterface:
    """
    Wraps a live SUMO simulation accessible via TraCI.

    In Phase A this returns stub data. In Phase B, start() → step loop → stop()
    will drive a real SUMO process and return actual telemetry.
    """

    def __init__(self, G, duration_s: int = 3600, seed: int = 42, scenario_id: int | None = None):
        self.G = G
        self.duration_s = duration_s
        self.seed = seed
        self.scenario_id = scenario_id
        self._is_running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start SUMO via TraCI. Returns True if successful."""
        if not TRACI_AVAILABLE:
            log.error("Cannot start SUMO: TraCI not available.")
            return False

        sumo_dir = SUMO_CFG.parent
        sumo_dir.mkdir(parents=True, exist_ok=True)

        try:
            log.info("Generating SUMO network and route configurations from graph...")
            import osmnx as ox
            import random
            import subprocess
            import shutil
            import networkx as nx
            
            G_proj = ox.project_graph(self.G)

            # 1. Write nodes.nod.xml
            nodes_xml_path = sumo_dir / "nodes.nod.xml"
            with open(nodes_xml_path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write('<nodes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/nodes_file.xsd">\n')
                for node_id, data in G_proj.nodes(data=True):
                    x = data.get("x", 0.0)
                    y = data.get("y", 0.0)
                    is_signal = data.get("highway") == "traffic_signals"
                    node_type = 'traffic_light' if is_signal else 'priority'
                    f.write(f'    <node id="{node_id}" x="{x:.3f}" y="{y:.3f}" type="{node_type}"/>\n')
                f.write('</nodes>\n')

            # 2. Write edges.edg.xml
            edges_xml_path = sumo_dir / "edges.edg.xml"
            with open(edges_xml_path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write('<edges xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/edges_file.xsd">\n')
                for u, v, k, data in G_proj.edges(data=True, keys=True):
                    edge_id = f"{u}_{v}_{k}"
                    
                    lanes = data.get("lanes", 1)
                    if isinstance(lanes, list):
                        lanes = lanes[0]
                    try:
                        lanes = int(lanes)
                    except (ValueError, TypeError):
                        lanes = 1
                        
                    speed = data.get("speed_kph", 40)
                    if isinstance(speed, list):
                        speed = speed[0]
                    try:
                        speed_mps = float(speed) / 3.6
                    except (ValueError, TypeError):
                        speed_mps = 11.11  # 40 kph
                        
                    f.write(f'    <edge id="{edge_id}" from="{u}" to="{v}" numLanes="{lanes}" speed="{speed_mps:.3f}"/>\n')
                f.write('</edges>\n')

            # 3. Compile network using netconvert
            sumo_home = os.environ.get("SUMO_HOME", "")
            if sumo_home:
                netconvert_bin = Path(sumo_home) / "bin" / "netconvert.exe"
                if not netconvert_bin.exists():
                    netconvert_bin = Path(sumo_home) / "bin" / "netconvert"
            else:
                netconvert_bin = Path("netconvert")

            if not netconvert_bin.exists() or not netconvert_bin.is_absolute():
                netconvert_path = shutil.which("netconvert")
                if netconvert_path:
                    netconvert_bin = Path(netconvert_path)

            log.info(f"Running netconvert binary: {netconvert_bin}")
            cmd_net = [
                str(netconvert_bin),
                "--node-files", str(nodes_xml_path),
                "--edge-files", str(edges_xml_path),
                "--output-file", str(sumo_dir / "network.net.xml"),
                "--no-warnings", "true"
            ]
            subprocess.run(cmd_net, check=True)
            log.info("SUMO network compiled successfully.")

            # 4. Generate random shortest-path vehicle routes using NetworkX
            routes_xml_path = sumo_dir / "routes.rou.xml"
            with open(routes_xml_path, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                f.write('<routes xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/routes_file.xsd">\n')
                
                # Write standard vehicle types matching mixed traffic behavior
                f.write('    <vType id="two-wheeler" accel="3.0" decel="5.0" sigma="0.7" length="2.0" minGap="1.5" maxSpeed="11.1" color="0.22,0.74,0.97"/>\n')
                f.write('    <vType id="auto" accel="2.2" decel="4.0" sigma="0.6" length="3.0" minGap="2.0" maxSpeed="9.7" color="0.65,0.55,0.98"/>\n')
                f.write('    <vType id="car" accel="2.6" decel="4.5" sigma="0.5" length="4.5" minGap="2.5" maxSpeed="13.8" color="0.06,0.73,0.51"/>\n')
                f.write('    <vType id="bus" accel="1.2" decel="3.5" sigma="0.4" length="10.0" minGap="3.0" maxSpeed="10.0" color="0.98,0.45,0.09"/>\n')

                nodes_list = list(G_proj.nodes())
                veh_id = 0
                
                random.seed(self.seed)
                for _ in range(450):
                    start_node = random.choice(nodes_list)
                    end_node = random.choice(nodes_list)
                    if start_node == end_node:
                        continue
                    try:
                        path = nx.shortest_path(G_proj, start_node, end_node)
                        if len(path) >= 2:
                            edges_path = []
                            for i in range(len(path) - 1):
                                u_n, v_n = path[i], path[i+1]
                                keys = list(G_proj[u_n][v_n].keys())
                                if keys:
                                    edges_path.append(f"{u_n}_{v_n}_{keys[0]}")
                            
                            if edges_path:
                                f.write(f'    <route id="r_{veh_id}" edges="{" ".join(edges_path)}"/>\n')
                                
                                r_val = random.random()
                                if r_val < 0.45:
                                    vtype = "two-wheeler"
                                elif r_val < 0.60:
                                    vtype = "auto"
                                elif r_val < 0.95:
                                    vtype = "car"
                                else:
                                    vtype = "bus"
                                    
                                f.write(f'    <vehicle id="v_{veh_id}" type="{vtype}" route="r_{veh_id}" depart="{random.randint(0, 300)}"/>\n')
                                veh_id += 1
                    except nx.NetworkXNoPath:
                        continue
                f.write('</routes>\n')
            log.info(f"Generated {veh_id} shortest-path routes.")

        except Exception as e:
            log.error(f"Error compiling SUMO network configurations: {e}")
            return False

        # Start TraCI
        sumo_binary = os.getenv("SUMO_BINARY", "sumo")
        if sumo_binary == "sumo" or not shutil.which(sumo_binary):
            sumo_home = os.environ.get("SUMO_HOME", "")
            if sumo_home:
                sumo_exe = Path(sumo_home) / "bin" / f"{sumo_binary}.exe"
                if not sumo_exe.exists():
                    sumo_exe = Path(sumo_home) / "bin" / sumo_binary
                if sumo_exe.exists():
                    sumo_binary = str(sumo_exe)
                    
        cmd = [
            sumo_binary,
            "-c", str(SUMO_CFG),
            "--seed", str(self.seed),
            "--no-warnings", "true",
            "--duration-log.statistics", "true",
        ]
        traci.start(cmd)
        self._is_running = True
        log.info(f"SUMO started with config {SUMO_CFG}")
        return True

    def stop(self) -> None:
        """Close the TraCI connection and SUMO process."""
        if TRACI_AVAILABLE and self._is_running:
            traci.close()
            self._is_running = False
            log.info("SUMO stopped.")

    # ── Step loop ─────────────────────────────────────────────────────────────

    def run_steps(self, step_length_s: float = 1.0, sample_interval: int = 10) -> list[dict]:
        """
        Run simulation step-by-step for self.duration_s seconds, collecting
        per-edge telemetry at sample intervals.

        Returns a list of step-level snapshots.
        """
        if not self._is_running:
            raise RuntimeError("SUMO is not running. Call start() first.")

        steps = int(self.duration_s / step_length_s)
        snapshots = []
        import numpy as np

        for step in range(steps):
            traci.simulationStep()
            if step % sample_interval == 0 or step == steps - 1:
                # Write progress file for frontend polling
                if self.scenario_id is not None:
                    import json
                    progress_pct = int(step / max(steps - 1, 1) * 100)
                    progress_file = ROOT / "data" / f"progress_{self.scenario_id}.json"
                    try:
                        with open(progress_file, "w") as pf:
                            json.dump({
                                "progress": progress_pct,
                                "step": step,
                                "total_steps": steps,
                                "status": "running"
                            }, pf)
                    except Exception:
                        pass

                snap = {}
                try:
                    # Get list of all active vehicles (usually <500) instead of all edges (~45,000)
                    veh_ids = traci.vehicle.getIDList()
                    edge_vehs = {}
                    for vid in veh_ids:
                        try:
                            eid = traci.vehicle.getRoadID(vid)
                            if eid.startswith(":"):
                                continue
                            speed = traci.vehicle.getSpeed(vid)
                            wait = traci.vehicle.getWaitingTime(vid)
                            if eid not in edge_vehs:
                                edge_vehs[eid] = []
                            edge_vehs[eid].append({"speed": speed, "wait": wait})
                        except Exception:
                            continue
                    
                    # Compute aggregated edge stats from the vehicles actually present on them
                    for eid, vehs in edge_vehs.items():
                        speeds = [v["speed"] for v in vehs]
                        waits = [v["wait"] for v in vehs]
                        snap[eid] = {
                            "mean_speed":    float(np.mean(speeds)) if speeds else 0.0,
                            "occupancy":     float(len(vehs) * 0.1),
                            "vehicle_count": int(len(vehs)),
                            "waiting_time":  float(np.sum(waits)) if waits else 0.0,
                        }
                except Exception as e:
                    log.error(f"Error in step sampling: {e}")
                snapshots.append(snap)

        return snapshots

    # ── Control (Phase B) ─────────────────────────────────────────────────────

    def set_phase(self, tl_id: str, phase_index: int) -> None:
        """Change a traffic light phase during live simulation."""
        if TRACI_AVAILABLE and self._is_running:
            traci.trafficlight.setPhase(tl_id, phase_index)

    def set_phase_duration(self, tl_id: str, duration_s: float) -> None:
        """Extend or shorten the current phase."""
        if TRACI_AVAILABLE and self._is_running:
            traci.trafficlight.setPhaseDuration(tl_id, duration_s)

    def reroute_vehicle(self, vehicle_id: str) -> None:
        """Reroute a vehicle along the current fastest path."""
        if TRACI_AVAILABLE and self._is_running:
            traci.vehicle.rerouteTraveltime(vehicle_id)

    # ── High-level run ────────────────────────────────────────────────────────

    def run(self) -> dict:
        """
        Full run: start → collect telemetry → stop → aggregate.

        Falls back to SyntheticSimulator if SUMO is not available.
        """
        if not TRACI_AVAILABLE:
            log.warning("Falling back to synthetic simulator.")
            from simulation.simulation_runner import SyntheticSimulator
            return SyntheticSimulator(self.G, self.duration_s, self.seed).run()

        if not self.start():
            log.warning("Could not start SUMO — falling back to synthetic simulator.")
            from simulation.simulation_runner import SyntheticSimulator
            return SyntheticSimulator(self.G, self.duration_s, self.seed).run()

        try:
            snapshots = self.run_steps()
            result = self._aggregate(snapshots)
        finally:
            self.stop()
            if self.scenario_id is not None:
                progress_file = ROOT / "data" / f"progress_{self.scenario_id}.json"
                if progress_file.exists():
                    try:
                        progress_file.unlink()
                    except Exception:
                        pass

        result["engine"] = "sumo"
        return result

    def _aggregate(self, snapshots: list[dict]) -> dict:
        """
        Aggregate step-level snapshots into the standard telemetry schema.
        Maps values back to standard OSMnx edge graph nodes and aggregates statistics.
        """
        import numpy as np
        log.info(f"Aggregating {len(snapshots)} simulation steps …")
        
        edges_out = []
        for u, v, k, data in self.G.edges(data=True, keys=True):
            edge_id = f"{u}_{v}_{k}"
            
            speeds = []
            occupancies = []
            counts = []
            wait_times = []
            
            for snap in snapshots:
                if edge_id in snap:
                    speeds.append(snap[edge_id]["mean_speed"])
                    occupancies.append(snap[edge_id]["occupancy"])
                    counts.append(snap[edge_id]["vehicle_count"])
                    wait_times.append(snap[edge_id]["waiting_time"])
            
            # If no data collected (e.g. no vehicles traversed), fall back to base road specs
            avg_speed_sim = np.mean(speeds) * 3.6 if speeds else float(data.get("speed_kph", 40))
            if avg_speed_sim <= 0:
                avg_speed_sim = float(data.get("speed_kph", 40))
                
            avg_occ = np.mean(occupancies) if occupancies else 0.0
            avg_count = np.mean(counts) if counts else 0.0
            avg_wait = np.mean(wait_times) if wait_times else 0.0
            
            lanes_val = data.get("lanes", 1)
            if isinstance(lanes_val, list):
                lanes_val = lanes_val[0]
            try:
                lanes_val = int(lanes_val)
            except (ValueError, TypeError):
                lanes_val = 1
                
            length_val = float(data.get("length", 120.0))
            free_flow_speed = float(data.get("speed_kph", 40))
            
            # Synthesize flow representation
            flow_val = avg_count * 120.0  # approximate simulated throughput
            
            edges_out.append({
                "edge_id": edge_id,
                "u": u, "v": v,
                "length_m": length_val,
                "road_type": str(data.get("highway", "residential")),
                "lanes": lanes_val,
                "speed_kph": free_flow_speed,
                "capacity": lanes_val * 900,
                "flow": round(flow_val, 1),
                "speed_sim": round(avg_speed_sim, 1),
                "density": round(avg_count * 10.0, 2),
                "queue_length": round(avg_wait / 10.0, 2),
                "wait_time": round(avg_wait, 1),
                "travel_time": round(length_val / max(avg_speed_sim / 3.6, 0.5), 1),
                "occupancy": round(avg_occ, 3),
            })

        nodes_out = []
        for node_id, data in self.G.nodes(data=True):
            is_signal = data.get("highway") == "traffic_signals"
            
            # Derive node average waiting time from its incoming edges
            node_incoming_waits = [e["wait_time"] for e in edges_out if e["v"] == node_id]
            avg_wait = np.mean(node_incoming_waits) if node_incoming_waits else 0.0
            
            has_sidewalk = False
            for u_e, v_e, k_e, edata in self.G.edges(data=True, keys=True):
                if u_e == node_id or v_e == node_id:
                    if edata.get("sidewalk_width", 0.0) > 0.0:
                        has_sidewalk = True
                        break

            nodes_out.append({
                "node_id": node_id,
                "lat": float(data.get("y", 14.4644)),
                "lon": float(data.get("x", 75.9218)),
                "street_count": int(data.get("street_count", 3)),
                "conflict_rate": round(avg_wait * 0.12, 2) if is_signal else round(avg_wait * 0.02, 2),
                "avg_wait_time": round(avg_wait, 1),
                "highway": data.get("highway"),
                "designation": data.get("designation"),
                "has_sidewalk": has_sidewalk,
                "has_dustbin": data.get("has_dustbin", False),
            })

        tts = [e["travel_time"] for e in edges_out]
        waits = [e["wait_time"] for e in edges_out]
        speeds = [e["speed_sim"] for e in edges_out]
        flows = [e["flow"] for e in edges_out]
        congested = sum(1 for e in edges_out if e["speed_sim"] / e["speed_kph"] < 0.45)
        
        summary = {
            "avg_travel_time_s":  round(float(np.mean(tts)), 2) if tts else 0.0,
            "avg_wait_time_s":    round(float(np.mean(waits)), 2) if waits else 0.0,
            "avg_speed_kph":      round(float(np.mean(speeds)), 2) if speeds else 0.0,
            "total_flow_veh_h":   round(float(np.sum(flows)), 0) if flows else 0.0,
            "congested_edges":    congested,
            "congestion_ratio":   round(congested / max(len(edges_out), 1), 4),
        }
        
        return {
            "engine": "sumo",
            "edges": edges_out,
            "nodes": nodes_out,
            "summary": summary,
        }
