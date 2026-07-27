"""
ai/issue_detection/intersection_safety_analyzer.py
────────────────────────────────────────────────────────
Flags intersections with elevated conflict potential.

Conflict signals used
──────────────────────
  • conflict_rate   — simulated vehicle conflicts per hour at the node
  • avg_wait_time   — average wait time at the intersection (s)
  • street_count    — number of approaches (higher → more conflict potential)
  • incoming flow   — sum of flows on all incoming edges

Severity thresholds (defaults)
───────────────────────────────
  severe   : conflict_rate > 2.0  OR  avg_wait_time > 60s
  moderate : conflict_rate > 1.0  OR  avg_wait_time > 35s
  low      : conflict_rate > 0.5  OR  avg_wait_time > 20s
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("intersection_safety_analyzer")


def _make_issue(issue_id, node_id, lat, lon, severity, metrics, description):
    return {
        "issue_id":    issue_id,
        "type":        "intersection_safety",
        "severity":    severity,
        "location": {
            "node_id": node_id,
            "lat":     lat,
            "lon":     lon,
        },
        "metrics":     metrics,
        "description": description,
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }


class IntersectionSafetyAnalyzer:
    """Detect unsafe intersections from node-level telemetry."""

    def __init__(
        self,
        conflict_severe:     float = 2.0,
        conflict_moderate:   float = 1.0,
        conflict_low:        float = 0.5,
        wait_severe:         float = 60.0,
        wait_moderate:       float = 35.0,
        wait_low:            float = 20.0,
        min_street_count:    int   = 3,     # only flag junctions, not dead-ends
    ):
        self.conflict_severe   = conflict_severe
        self.conflict_moderate = conflict_moderate
        self.conflict_low      = conflict_low
        self.wait_severe       = wait_severe
        self.wait_moderate     = wait_moderate
        self.wait_low          = wait_low
        self.min_street_count  = min_street_count

    def detect(self, telemetry: dict) -> list[dict]:
        nodes  = telemetry.get("nodes", [])
        issues = []
        counter = 0

        for node in nodes:
            sc   = node.get("street_count", 1)
            if sc < self.min_street_count:
                continue  # not a proper intersection

            node_id      = node["node_id"]
            lat          = node.get("lat", 0)
            lon          = node.get("lon", 0)
            conflict     = node.get("conflict_rate", 0)
            wait         = node.get("avg_wait_time", 0)

            # Determine severity
            if conflict > self.conflict_severe or wait > self.wait_severe:
                severity = "severe"
            elif conflict > self.conflict_moderate or wait > self.wait_moderate:
                severity = "moderate"
            elif conflict > self.conflict_low or wait > self.wait_low:
                severity = "low"
            else:
                continue

            counter += 1
            issue_id = f"intersection_{node_id}_{counter}"
            desc = (
                f"Unsafe intersection at node {node_id} "
                f"({sc}-way junction, lat={lat:.5f}, lon={lon:.5f}). "
                f"Conflict rate: {conflict:.2f}/h. "
                f"Avg wait time: {wait:.1f}s."
            )
            issues.append(_make_issue(
                issue_id=issue_id,
                node_id=node_id,
                lat=lat,
                lon=lon,
                severity=severity,
                metrics={
                    "conflict_rate":   round(conflict, 3),
                    "avg_wait_time_s": round(wait, 2),
                    "street_count":    sc,
                },
                description=desc,
            ))

        log.info(f"IntersectionSafetyAnalyzer: {len(issues)} issues from {len(nodes)} nodes.")
        priority = {"severe": 0, "moderate": 1, "low": 2}
        issues.sort(key=lambda x: priority.get(x["severity"], 3))
        return issues


def detect_unsafe_intersections(telemetry: dict, **kwargs) -> list[dict]:
    return IntersectionSafetyAnalyzer(**kwargs).detect(telemetry)
