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
import threading
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger("traci_interface")

ROOT = Path(__file__).resolve().parent.parent
SUMO_CFG = ROOT / "simulation" / "sumo_config" / "simulation.sumocfg"

# Global lock: only one SUMO process at a time (TraCI default label is shared)
_SUMO_LOCK = threading.Lock()


# ── Try importing TraCI ───────────────────────────────────────────────────────
try:
    import traci  # type: ignore
    TRACI_AVAILABLE = True
    log.info("TraCI imported successfully — SUMO integration is available.")
except ImportError:
    TRACI_AVAILABLE = False
    log.warning(
        "TraCI not available (pip install eclipse-sumo or traci). "
        "Using synthetic simulation fallback."
    )


# ── Lazy SUMO binary detection ──────────────────────────────────────────────

def _get_sumo_info() -> dict:
    """Return cached SUMO detection result (sumo_detector.detect_sumo)."""
    try:
        from simulation.sumo_detector import detect_sumo
        return detect_sumo()
    except Exception as exc:
        log.warning(f"sumo_detector failed: {exc}")
        return {"available": False, "sumo_bin": None, "netconvert_bin": None}


def _emit_progress(scenario_id: int | None, data: dict):
    if scenario_id is None:
        return
    import json
    import time
    progress_file = ROOT / "data" / f"progress_{scenario_id}.json"
    try:
        current = {}
        if progress_file.exists():
            try:
                with open(progress_file, "r") as f:
                    current = json.load(f)
            except Exception:
                current = {}
        
        # Keep track of pipeline start timestamp if available
        started_timestamp = current.get("started_timestamp")
        if not started_timestamp:
            started_timestamp = data.get("started_timestamp") or time.time()
            data["started_timestamp"] = started_timestamp

        now = time.time()
        data["elapsed_s"] = round(now - started_timestamp, 1)
        current.update(data)
        with open(progress_file, "w") as pf:
            json.dump(current, pf)
    except Exception:
        pass


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
        # Unique label per run — prevents KeyError when multiple runs coexist
        self._label = f"sumo_{uuid.uuid4().hex[:8]}"

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start SUMO via TraCI. Returns True if successful."""
        if not TRACI_AVAILABLE:
            log.error("Cannot start SUMO: TraCI not available.")
            return False

        sumo_dir = SUMO_CFG.parent
        sumo_dir.mkdir(parents=True, exist_ok=True)

        _emit_progress(self.scenario_id, {
            "progress": 2,
            "status": "running",
            "stage": "building_network",
            "stage_label": "Compiling SUMO network topology...",
        })

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

            _emit_progress(self.scenario_id, {
                "progress": 4,
                "status": "running",
                "stage": "generating_routes",
                "stage_label": "Generating vehicle trips & routing...",
            })

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

        # Start TraCI — use sumo_detector for reliable binary resolution
        sumo_info = _get_sumo_info()
        if not sumo_info["available"] or not sumo_info["sumo_bin"]:
            log.error(
                "SUMO binary not found. "
                "Set SUMO_HOME in .env or install SUMO from https://sumo.dlr.de"
            )
            return False

        sumo_binary = sumo_info["sumo_bin"]
        netconvert_binary = sumo_info.get("netconvert_bin") or "netconvert"

        # Replace ad-hoc netconvert path in the compile step above with detected binary
        # (The XML files are already written; we just fix the compile call)
        try:
            sumo_dir = SUMO_CFG.parent
            import subprocess
            cmd_net_fix = [
                str(netconvert_binary),
                "--node-files", str(sumo_dir / "nodes.nod.xml"),
                "--edge-files", str(sumo_dir / "edges.edg.xml"),
                "--output-file", str(sumo_dir / "network.net.xml"),
                "--no-warnings", "true"
            ]
            subprocess.run(cmd_net_fix, check=True, capture_output=True)
            log.info("SUMO network compiled via sumo_detector binary.")
        except Exception as net_err:
            log.warning(f"netconvert compile (post-start) skipped: {net_err}")

        _emit_progress(self.scenario_id, {
            "progress": 6,
            "status": "running",
            "stage": "simulating",
            "stage_label": "Starting SUMO TraCI engine...",
        })

        cmd = [
            str(sumo_binary),
            "-c", str(SUMO_CFG),
            "--seed", str(self.seed),
            "--no-warnings", "true",
            "--duration-log.statistics", "true",
        ]
        traci.start(cmd, label=self._label)
        self._is_running = True
        log.info(f"SUMO started with config {SUMO_CFG} (label={self._label})")
        return True

    def stop(self) -> None:
        """Close the TraCI connection and SUMO process (safe even if already closed)."""
        if not TRACI_AVAILABLE or not self._is_running:
            return
        try:
            conn = traci.getConnection(self._label)
            conn.close()
        except Exception:
            # Connection already gone — fine
            pass
        finally:
            self._is_running = False
            log.info(f"SUMO stopped (label={self._label}).")

    # ── Step loop ─────────────────────────────────────────────────────────────

    def run_steps(self, step_length_s: float = 1.0, sample_interval: int = 5) -> list[dict]:
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
        import time

        conn = traci.getConnection(self._label)
        step_loop_start = time.time()

        for step in range(steps):
            conn.simulationStep()
            steps_done = step + 1

            if step % sample_interval == 0 or step == steps - 1:
                # Active vehicles in the simulation network
                veh_ids = []
                try:
                    veh_ids = traci.vehicle.getIDList()
                except Exception:
                    pass

                # Dynamic step rate and ETA calculation
                now = time.time()
                elapsed_loop_s = max(now - step_loop_start, 0.001)
                steps_per_s = steps_done / elapsed_loop_s
                remaining_steps = max(steps - steps_done, 0)
                sim_eta_s = remaining_steps / max(steps_per_s, 0.001)
                # Post-processing buffer (aggregation + metrics + AI proposal optimization)
                total_eta_s = sim_eta_s + 3.0 if remaining_steps > 0 else 2.0

                # Map steps to 6% - 85% progress range
                progress_pct = round(6.0 + (steps_done / max(steps, 1)) * 79.0, 1)

                _emit_progress(self.scenario_id, {
                    "progress": progress_pct,
                    "step": steps_done,
                    "total_steps": steps,
                    "status": "running",
                    "stage": "simulating",
                    "stage_label": f"Simulating TraCI step {steps_done}/{steps} ({steps_per_s:.1f} steps/s)",
                    "steps_per_s": round(steps_per_s, 1),
                    "eta_s": max(0.5, round(total_eta_s, 1)),
                    "active_vehicles": len(veh_ids),
                })

                snap = {}
                try:
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

        Raises RuntimeError if SUMO is explicitly requested but not available.
        Caller (simulation_runner.py) is responsible for catching this and
        returning a 503 to the API layer.
        """
        if not TRACI_AVAILABLE:
            raise RuntimeError(
                "TraCI Python package not installed. "
                "Run: pip install eclipse-sumo   (or: pip install traci)"
            )

        sumo_info = _get_sumo_info()
        if not sumo_info["available"]:
            raise RuntimeError(
                "SUMO binary not found on this machine. "
                "Install SUMO from https://sumo.dlr.de/docs/Downloads.php "
                "and set SUMO_HOME in your .env file."
            )

        if not _SUMO_LOCK.acquire(timeout=600):
            log.error("Could not acquire SUMO lock within 10 minutes — another simulation is still running.")
            from simulation.simulation_runner import SyntheticSimulator
            return SyntheticSimulator(self.G, self.duration_s, self.seed).run()

        try:
            if not self.start():
                log.warning("Could not start SUMO — falling back to synthetic simulator.")
                _SUMO_LOCK.release()
                from simulation.simulation_runner import SyntheticSimulator
                return SyntheticSimulator(self.G, self.duration_s, self.seed).run()

            try:
                snapshots = self.run_steps()
                _emit_progress(self.scenario_id, {
                    "progress": 85,
                    "stage": "aggregating",
                    "stage_label": "Aggregating telemetry & simulation snapshots...",
                    "status": "running",
                    "eta_s": 3.0
                })
                result = self._aggregate(snapshots)
            finally:
                self.stop()
        finally:
            _SUMO_LOCK.release()

        result["engine"] = "sumo"
        return result

    def _aggregate(self, snapshots: list[dict]) -> dict:
        """
        Aggregate step-level snapshots into the standard telemetry schema.
        Maps values back to standard OSMnx edge graph nodes and aggregates statistics.
        """
        import numpy as np
        log.info(f"Aggregating {len(snapshots)} simulation steps …")
        
        # Pre-group snapshot values by edge_id (highly optimized O(E + S) pass)
        edge_data_accum = {}
        for snap in snapshots:
            for edge_id, stats in snap.items():
                if edge_id not in edge_data_accum:
                    edge_data_accum[edge_id] = {
                        "speeds": [], "occupancies": [], "counts": [], "wait_times": []
                    }
                accum = edge_data_accum[edge_id]
                accum["speeds"].append(stats["mean_speed"])
                accum["occupancies"].append(stats["occupancy"])
                accum["counts"].append(stats["vehicle_count"])
                accum["wait_times"].append(stats["waiting_time"])

        edges_out = []
        for u, v, k, data in self.G.edges(data=True, keys=True):
            edge_id = f"{u}_{v}_{k}"
            
            accum = edge_data_accum.get(edge_id)
            if accum:
                speeds = accum["speeds"]
                occupancies = accum["occupancies"]
                counts = accum["counts"]
                wait_times = accum["wait_times"]
            else:
                speeds = []
                occupancies = []
                counts = []
                wait_times = []
            
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
