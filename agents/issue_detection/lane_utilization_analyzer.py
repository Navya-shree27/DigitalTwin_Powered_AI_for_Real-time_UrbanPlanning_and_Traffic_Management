"""
agents/issue_detection/lane_utilization_analyzer.py
─────────────────────────────────────────────────────
Flags road segments with anomalous lane utilization:
  • Underutilized : occupancy < 0.20 on a multi-lane road (wasted capacity)
  • Saturated     : occupancy > 0.90 (lane at or beyond capacity)

The analyzer also flags lanes with disproportionate imbalance relative to
adjacent parallel edges (future extension, Phase C+).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("lane_utilization_analyzer")


def _make_issue(issue_id, edge_id, u, v, subtype, severity, metrics, description):
    return {
        "issue_id":    issue_id,
        "type":        "lane_utilization",
        "subtype":     subtype,     # "underutilized" | "saturated"
        "severity":    severity,
        "location": {
            "edge_id": edge_id,
            "node_u":  u,
            "node_v":  v,
        },
        "metrics":     metrics,
        "description": description,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


class LaneUtilizationAnalyzer:
    """Detect under/over-utilized lanes from edge-level telemetry."""

    def __init__(
        self,
        underutilized_threshold: float = 0.20,
        saturated_threshold:     float = 0.90,
        min_lanes_for_underuse:  int   = 2,       # only flag multi-lane underuse
    ):
        self.underutilized_threshold = underutilized_threshold
        self.saturated_threshold     = saturated_threshold
        self.min_lanes_for_underuse  = min_lanes_for_underuse

    def detect(self, telemetry: dict) -> list[dict]:
        edges  = telemetry.get("edges", [])
        issues = []
        counter = 0

        for edge in edges:
            edge_id  = edge["edge_id"]
            u        = edge["u"]
            v        = edge["v"]
            occupancy = edge.get("occupancy", 0)
            lanes    = edge.get("lanes", 1)
            road_type = edge.get("road_type", "road")
            speed    = edge.get("speed_sim", 40)
            flow     = edge.get("flow", 0)
            capacity = edge.get("capacity", 800)

            subtype = severity = None

            # Underutilized multi-lane road
            if lanes >= self.min_lanes_for_underuse and occupancy < self.underutilized_threshold:
                subtype = "underutilized"
                severity = "low" if occupancy > 0.10 else "moderate"

            # Saturated lane
            elif occupancy > self.saturated_threshold:
                subtype = "saturated"
                severity = "severe" if occupancy > 0.97 else "moderate"

            if subtype is None:
                continue

            counter += 1
            issue_id = f"lane_{subtype}_{edge_id}_{counter}"
            desc = (
                f"{'Underutilized' if subtype == 'underutilized' else 'Saturated'} lane on "
                f"edge {edge_id} ({road_type}, {lanes} lanes). "
                f"Occupancy: {occupancy:.1%}. Flow: {flow:.0f} veh/h. Capacity: {capacity} veh/h."
            )
            issues.append(_make_issue(
                issue_id=issue_id,
                edge_id=edge_id,
                u=u,
                v=v,
                subtype=subtype,
                severity=severity,
                metrics={
                    "occupancy":      round(occupancy, 4),
                    "lanes":          lanes,
                    "flow_veh_h":     round(flow, 2),
                    "capacity_veh_h": int(capacity),
                    "speed_sim_kph":  round(speed, 2),
                },
                description=desc,
            ))

        log.info(f"LaneUtilizationAnalyzer: {len(issues)} issues from {len(edges)} edges.")
        priority = {"severe": 0, "moderate": 1, "low": 2}
        issues.sort(key=lambda x: priority.get(x["severity"], 3))
        return issues


def detect_lane_issues(telemetry: dict, **kwargs) -> list[dict]:
    return LaneUtilizationAnalyzer(**kwargs).detect(telemetry)
