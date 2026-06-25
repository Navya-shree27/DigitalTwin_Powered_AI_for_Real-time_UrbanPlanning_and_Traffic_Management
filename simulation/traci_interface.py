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

    def __init__(self, G, duration_s: int = 3600, seed: int = 42):
        self.G = G
        self.duration_s = duration_s
        self.seed = seed
        self._is_running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Start SUMO via TraCI. Returns True if successful."""
        if not TRACI_AVAILABLE:
            log.error("Cannot start SUMO: TraCI not available.")
            return False
        if not SUMO_CFG.exists():
            log.error(f"SUMO config not found at {SUMO_CFG}. Run osm_to_network.py first.")
            return False

        sumo_binary = os.getenv("SUMO_BINARY", "sumo-gui")
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

    def run_steps(self, step_length_s: float = 1.0) -> list[dict]:
        """
        Run simulation step-by-step for self.duration_s seconds, collecting
        per-edge telemetry at each step.

        Returns a list of step-level snapshots.
        """
        if not self._is_running:
            raise RuntimeError("SUMO is not running. Call start() first.")

        steps = int(self.duration_s / step_length_s)
        snapshots = []

        for _ in range(steps):
            traci.simulationStep()
            edge_ids = traci.edge.getIDList()
            snap = {}
            for eid in edge_ids:
                snap[eid] = {
                    "mean_speed":    traci.edge.getLastStepMeanSpeed(eid),
                    "occupancy":     traci.edge.getLastStepOccupancy(eid),
                    "vehicle_count": traci.edge.getLastStepVehicleNumber(eid),
                    "waiting_time":  traci.edge.getWaitingTime(eid),
                }
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

        result["engine"] = "sumo"
        return result

    def _aggregate(self, snapshots: list[dict]) -> dict:
        """
        Aggregate step-level snapshots into the standard telemetry schema.
        (Phase B implementation — currently returns stub.)
        """
        # TODO (Phase B): average step-level values across the simulation window
        log.info(f"Aggregating {len(snapshots)} simulation steps …")
        return {
            "engine": "sumo",
            "edges": [],
            "nodes": [],
            "summary": {
                "avg_travel_time_s": 0,
                "avg_wait_time_s": 0,
                "avg_speed_kph": 0,
                "total_flow_veh_h": 0,
                "congested_edges": 0,
                "congestion_ratio": 0,
            },
        }
