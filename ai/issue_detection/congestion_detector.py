"""
ai/issue_detection/congestion_detector.py
──────────────────────────────────────────────
Rule-based congestion detector.

Flags road segments where simulated traffic conditions exceed congestion
thresholds based on speed drop, occupancy, queue length, or flow-to-capacity
ratio.

Every flagged issue is returned as a structured dict conforming to the
IssueRecord schema used by the rest of the pipeline.

Thresholds (adjustable via .env or constructor kwargs)
──────────────────────────────────────────────────────
  CONGESTION_SPEED_RATIO   < 0.40  → severe   (sim_speed / free_flow_speed)
  CONGESTION_SPEED_RATIO   < 0.65  → moderate
  CONGESTION_OCCUPANCY     > 0.80  → severe    (flow / capacity)
  CONGESTION_OCCUPANCY     > 0.65  → moderate
  CONGESTION_QUEUE_MIN     > 5     vehicles queued
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("congestion_detector")


# ─────────────────────────────────────────────────────────────────────────────
# Issue record factory
# ─────────────────────────────────────────────────────────────────────────────

def _make_issue(
    issue_id: str,
    location_edge_id: str,
    u: int,
    v: int,
    severity: str,
    metrics: dict,
    description: str,
) -> dict:
    return {
        "issue_id":    issue_id,
        "type":        "congestion",
        "severity":    severity,            # "low" | "moderate" | "severe"
        "location": {
            "edge_id": location_edge_id,
            "node_u":  u,
            "node_v":  v,
        },
        "metrics":     metrics,
        "description": description,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Detector
# ─────────────────────────────────────────────────────────────────────────────

class CongestionDetector:
    """
    Analyses edge-level telemetry and returns a list of congestion issues.

    Parameters
    ──────────
    speed_ratio_severe   : sim_speed / free_flow below this → severe
    speed_ratio_moderate : sim_speed / free_flow below this → moderate
    occupancy_severe     : occupancy above this → severe
    occupancy_moderate   : occupancy above this → moderate
    queue_min            : min queue length to flag as an issue
    """

    def __init__(
        self,
        speed_ratio_severe:   float = 0.40,
        speed_ratio_moderate: float = 0.65,
        occupancy_severe:     float = 0.80,
        occupancy_moderate:   float = 0.65,
        queue_min:            float = 5.0,
    ):
        self.speed_ratio_severe   = speed_ratio_severe
        self.speed_ratio_moderate = speed_ratio_moderate
        self.occupancy_severe     = occupancy_severe
        self.occupancy_moderate   = occupancy_moderate
        self.queue_min            = queue_min

    def detect(self, telemetry: dict) -> list[dict]:
        """
        Run detection on a telemetry dict produced by simulation_runner.

        Returns a list of IssueRecord dicts (may be empty).
        """
        edges   = telemetry.get("edges", [])
        issues  = []
        counter = 0

        for edge in edges:
            edge_id   = edge["edge_id"]
            u         = edge["u"]
            v         = edge["v"]
            speed_ff  = edge.get("speed_kph", 40)
            speed_sim = edge.get("speed_sim", speed_ff)
            occupancy = edge.get("occupancy", 0)
            queue     = edge.get("queue_length", 0)
            wait      = edge.get("wait_time", 0)
            flow      = edge.get("flow", 0)
            capacity  = edge.get("capacity", 800)

            speed_ratio = speed_sim / max(speed_ff, 1)

            # Determine severity
            severity = None
            if speed_ratio < self.speed_ratio_severe or occupancy > self.occupancy_severe:
                severity = "severe"
            elif speed_ratio < self.speed_ratio_moderate or occupancy > self.occupancy_moderate:
                severity = "moderate"
            elif queue > self.queue_min:
                severity = "low"

            if severity is None:
                continue

            counter += 1
            issue_id = f"congestion_{edge_id}_{counter}"

            desc = (
                f"Congestion detected on edge {edge_id} ({edge.get('road_type', 'road')}). "
                f"Simulated speed {speed_sim:.1f} km/h vs free-flow {speed_ff:.1f} km/h "
                f"(ratio {speed_ratio:.2f}). Occupancy {occupancy:.1%}. "
                f"Queue length {queue:.1f} vehicles. Wait time {wait:.1f}s."
            )

            issues.append(_make_issue(
                issue_id=issue_id,
                location_edge_id=edge_id,
                u=u,
                v=v,
                severity=severity,
                metrics={
                    "speed_kph":      round(speed_sim, 2),
                    "free_flow_kph":  round(speed_ff, 2),
                    "speed_ratio":    round(speed_ratio, 4),
                    "occupancy":      round(occupancy, 4),
                    "queue_length":   round(queue, 2),
                    "wait_time_s":    round(wait, 2),
                    "flow_veh_h":     round(flow, 2),
                    "capacity_veh_h": int(capacity),
                },
                description=desc,
            ))

        log.info(f"CongestionDetector: {len(issues)} issues flagged from {len(edges)} edges.")
        # Sort: severe first, then moderate, then low
        priority = {"severe": 0, "moderate": 1, "low": 2}
        issues.sort(key=lambda x: priority.get(x["severity"], 3))
        return issues


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function
# ─────────────────────────────────────────────────────────────────────────────

def detect_congestion(telemetry: dict, **kwargs) -> list[dict]:
    """Module-level shorthand for CongestionDetector().detect(telemetry)."""
    return CongestionDetector(**kwargs).detect(telemetry)
