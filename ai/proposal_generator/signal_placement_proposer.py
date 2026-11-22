"""
Generates proposals for adding/removing/relocating traffic signals.
"""
import logging
import uuid
from typing import Any

log = logging.getLogger("signal_placement_proposer")


def generate_signal_placement_proposals(issues: list[dict], telemetry: dict) -> list[dict]:
    """
    Generate proposals from signal_placement issues.
    Each proposal is a standard proposal dict with type signal_add or signal_remove.
    """
    proposals = []
    for issue in issues:
        if issue.get("type") != "signal_placement":
            continue
        subtype = issue.get("subtype")
        metrics = issue.get("metrics", {})
        loc = issue.get("location", {})
        node_id = loc.get("node_id", metrics.get("node_id", "?"))

        if subtype == "signal_add":
            proposals.append({
                "proposal_id": f"sig_add_{node_id}_{uuid.uuid4().hex[:6]}",
                "type": "signal_add",
                "subtype": "signal_add",
                "description": (
                    f"Install traffic signal at intersection node {node_id} "
                    f"({metrics.get('street_count', '?')}-way junction, "
                    f"conflict rate {metrics.get('conflict_rate', 0):.2f}). "
                    f"Webster-timed green phase recommended."
                ),
                "parameters": {
                    "node_id": node_id,
                    "lat": loc.get("lat", 0.0),
                    "lon": loc.get("lon", 0.0),
                    "street_count": metrics.get("street_count", 4),
                    "recommended_green_s": 35,
                    "recommended_cycle_s": 90,
                },
                "expected_improvement": {
                    "conflict_rate_reduction_pct": 40,
                    "avg_wait_reduction_pct": 15,
                    "safety_score_increase": 25,
                },
            })
        elif subtype == "signal_remove":
            proposals.append({
                "proposal_id": f"sig_rem_{node_id}_{uuid.uuid4().hex[:6]}",
                "type": "signal_remove",
                "subtype": "signal_remove",
                "description": (
                    f"Remove redundant traffic signal at node {node_id} "
                    f"(avg wait {metrics.get('avg_wait_time', 0):.1f}s, "
                    f"conflict rate {metrics.get('conflict_rate', 0):.2f}). "
                    f"Replace with yield/stop sign."
                ),
                "parameters": {
                    "node_id": node_id,
                    "lat": loc.get("lat", 0.0),
                    "lon": loc.get("lon", 0.0),
                    "replacement": "yield_sign",
                },
                "expected_improvement": {
                    "avg_speed_increase_pct": 8,
                    "avg_wait_reduction_pct": 20,
                },
            })
    log.info(f"Signal placement proposals: {len(proposals)} generated")
    return proposals
