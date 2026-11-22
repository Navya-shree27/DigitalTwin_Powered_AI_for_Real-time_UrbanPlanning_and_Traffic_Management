"""
Analyzes intersections to recommend where to ADD or REMOVE traffic signals.
Returns issues in the standard format used by congestion_detector.py
"""
import logging
from typing import Any

log = logging.getLogger("signal_placement_analyzer")

ADD_THRESHOLD_STREET_COUNT = 4   # 4+ streets → candidate for signal
ADD_CONFLICT_RATE_MAX = 0.6      # conflict rate must be < 0.6 to add signal (not already congested)
REMOVE_WAIT_MAX = 8.0            # avg_wait_time < 8s → candidate for removal
REMOVE_CONFLICT_MAX = 0.15       # very low conflict → safe to remove signal

def detect_signal_placement_issues(telemetry: dict, existing_signal_osmids: set | None = None) -> list[dict]:
    """
    Detect intersections where signals should be ADDED or REMOVED.
    Returns list of issue dicts.
    """
    issues = []
    nodes = telemetry.get("nodes", [])
    if not nodes:
        return []

    existing_signals = existing_signal_osmids or set()

    for node in nodes:
        node_id = str(node.get("node_id", ""))
        is_signal = str(node.get("highway", "")) == "traffic_signals" or node_id in existing_signals
        street_count = int(node.get("street_count", node.get("degree", 0)))
        avg_wait = float(node.get("avg_wait_time", node.get("wait_time_s", 0.0)))
        conflict_rate = float(node.get("conflict_rate", 0.0))
        lat = node.get("lat", 0.0)
        lon = node.get("lon", 0.0)

        # Recommend ADDING a signal
        if (not is_signal and 
            street_count >= ADD_THRESHOLD_STREET_COUNT and 
            conflict_rate < ADD_CONFLICT_RATE_MAX):
            issues.append({
                "issue_id": f"signal_add_{node_id}",
                "type": "signal_placement",
                "subtype": "signal_add",
                "severity": "moderate",
                "description": (
                    f"Intersection node {node_id} has {street_count} street connections "
                    f"and no traffic signal. Conflict rate: {conflict_rate:.2f}. "
                    f"A signal could improve safety and flow."
                ),
                "location": {"node_id": node_id, "lat": lat, "lon": lon},
                "metrics": {
                    "node_id": node_id,
                    "street_count": street_count,
                    "avg_wait_time": avg_wait,
                    "conflict_rate": conflict_rate,
                    "is_signal": False,
                    "recommendation": "add_signal",
                },
            })

        # Recommend REMOVING a signal
        elif (is_signal and
              avg_wait < REMOVE_WAIT_MAX and
              conflict_rate < REMOVE_CONFLICT_MAX and
              street_count <= 2):
            issues.append({
                "issue_id": f"signal_remove_{node_id}",
                "type": "signal_placement",
                "subtype": "signal_remove",
                "severity": "low",
                "description": (
                    f"Signal at intersection node {node_id} may be unnecessary: "
                    f"avg wait {avg_wait:.1f}s, conflict rate {conflict_rate:.2f}, "
                    f"{street_count} streets. Consider replacing with yield/stop sign."
                ),
                "location": {"node_id": node_id, "lat": lat, "lon": lon},
                "metrics": {
                    "node_id": node_id,
                    "street_count": street_count,
                    "avg_wait_time": avg_wait,
                    "conflict_rate": conflict_rate,
                    "is_signal": True,
                    "recommendation": "remove_signal",
                },
            })

    log.info(f"Signal placement analysis: {len(issues)} recommendations ({sum(1 for i in issues if i['subtype']=='signal_add')} add, {sum(1 for i in issues if i['subtype']=='signal_remove')} remove)")
    return issues
