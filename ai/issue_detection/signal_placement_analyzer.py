"""
Analyzes intersections to recommend where to ADD, REMOVE, or RELOCATE traffic signals.
Returns issues in the standard format used by congestion_detector.py
"""
import logging
from typing import Any

log = logging.getLogger("signal_placement_analyzer")

# Warrants for adding a signal (MUTCD-aligned heuristics for Indian city networks)
ADD_MIN_STREET_COUNT = 3       # 3+ approach arms (multi-way junction)
ADD_MIN_CONFLICT_RATE = 0.25    # High conflicting vehicular paths / hour
ADD_MIN_WAIT_TIME = 10.0       # Average unsignalized delay >= 10s

# Warrants for removing an underloaded/redundant signal
REMOVE_MAX_WAIT_TIME = 10.0    # Very low delay (< 10s)
REMOVE_MAX_CONFLICT = 0.20     # Minimal conflicting cross-traffic (< 0.20/h)
REMOVE_MAX_STREET_COUNT = 3    # 2 or 3 approaches where yield/stop sign suffices

# Warrants for relocating a misaligned signal
RELOCATE_MIN_WAIT = 14.0       # Significant queueing caused by offset approach geometry


def detect_signal_placement_issues(
    telemetry: dict,
    existing_signal_osmids: set | None = None,
) -> list[dict]:
    """
    Detect intersections where signals should be ADDED, REMOVED, or RELOCATED.
    Returns list of issue dicts.
    """
    issues = []
    nodes = telemetry.get("nodes", [])
    if not nodes:
        return []

    existing_signals = existing_signal_osmids or set()

    add_candidates = []
    remove_candidates = []
    relocate_candidates = []

    for node in nodes:
        node_id = str(node.get("node_id", ""))
        is_signal = str(node.get("highway", "")) == "traffic_signals" or node_id in existing_signals
        street_count = int(node.get("street_count", node.get("degree", 0)))
        avg_wait = float(node.get("avg_wait_time", node.get("wait_time_s", 0.0)))
        conflict_rate = float(node.get("conflict_rate", 0.0))
        lat = float(node.get("lat", 0.0))
        lon = float(node.get("lon", 0.0))

        # ── 1. Candidate to ADD a signal ─────────────────────────────────────
        # Unsignalized intersection with multiple approaches and high conflict or delay
        if not is_signal and street_count >= ADD_MIN_STREET_COUNT:
            if conflict_rate >= ADD_MIN_CONFLICT_RATE or avg_wait >= ADD_MIN_WAIT_TIME:
                priority_score = (conflict_rate * 2.0) + (street_count * 0.5) + (avg_wait / 10.0)
                add_candidates.append({
                    "node_id": node_id,
                    "street_count": street_count,
                    "avg_wait": avg_wait,
                    "conflict_rate": conflict_rate,
                    "lat": lat,
                    "lon": lon,
                    "score": priority_score,
                })

        # ── 2. Candidate to REMOVE a signal ──────────────────────────────────
        # Existing signal with minimal cross-traffic delay and low conflict
        elif is_signal:
            if (avg_wait < REMOVE_MAX_WAIT_TIME and
                conflict_rate < REMOVE_MAX_CONFLICT and
                street_count <= REMOVE_MAX_STREET_COUNT):
                remove_candidates.append({
                    "node_id": node_id,
                    "street_count": street_count,
                    "avg_wait": avg_wait,
                    "conflict_rate": conflict_rate,
                    "lat": lat,
                    "lon": lon,
                    "score": avg_wait + (conflict_rate * 5.0),
                })

            # ── 3. Candidate to RELOCATE a signal ────────────────────────────
            # Existing signal at a junction with high delay where slight offset relocation
            # aligns conflicting lanes and reduces turning blockages
            elif avg_wait >= RELOCATE_MIN_WAIT and street_count >= 3:
                relocate_candidates.append({
                    "node_id": node_id,
                    "street_count": street_count,
                    "avg_wait": avg_wait,
                    "conflict_rate": conflict_rate,
                    "lat": lat,
                    "lon": lon,
                    "score": avg_wait * conflict_rate,
                })

    # Sort and cap candidates to avoid flooding the planner
    # Add top 8 most critical intersections to signalize
    add_candidates.sort(key=lambda x: x["score"], reverse=True)
    for cand in add_candidates[:8]:
        nid = cand["node_id"]
        sc = cand["street_count"]
        cr = cand["conflict_rate"]
        wt = cand["avg_wait"]
        issues.append({
            "issue_id": f"signal_add_{nid}",
            "type": "signal_placement",
            "subtype": "signal_add",
            "severity": "severe" if cr >= 0.8 or wt >= 25.0 else "moderate",
            "description": (
                f"Intersection node {nid} ({sc}-way junction) lacks traffic signal. "
                f"Conflict rate is {cr:.2f}/h with {wt:.1f}s average delay. "
                f"Installing a signal will regulate conflicting movements."
            ),
            "location": {"node_id": nid, "lat": cand["lat"], "lon": cand["lon"]},
            "metrics": {
                "node_id": nid,
                "street_count": sc,
                "avg_wait_time": wt,
                "conflict_rate": cr,
                "is_signal": False,
                "recommendation": "add_signal",
            },
        })

    # Add top 4 underloaded signals to remove or downgrade
    remove_candidates.sort(key=lambda x: x["score"])
    for cand in remove_candidates[:4]:
        nid = cand["node_id"]
        sc = cand["street_count"]
        cr = cand["conflict_rate"]
        wt = cand["avg_wait"]
        issues.append({
            "issue_id": f"signal_remove_{nid}",
            "type": "signal_placement",
            "subtype": "signal_remove",
            "severity": "low",
            "description": (
                f"Traffic signal at node {nid} ({sc} approaches) is underloaded: "
                f"only {wt:.1f}s wait and {cr:.2f}/h conflict rate. "
                f"Consider removing or replacing with yield/stop sign to prevent stopping delay."
            ),
            "location": {"node_id": nid, "lat": cand["lat"], "lon": cand["lon"]},
            "metrics": {
                "node_id": nid,
                "street_count": sc,
                "avg_wait_time": wt,
                "conflict_rate": cr,
                "is_signal": True,
                "recommendation": "remove_signal",
            },
        })

    # Add top 3 signals to relocate/reposition
    relocate_candidates.sort(key=lambda x: x["score"], reverse=True)
    for cand in relocate_candidates[:3]:
        nid = cand["node_id"]
        sc = cand["street_count"]
        cr = cand["conflict_rate"]
        wt = cand["avg_wait"]
        # Calculate slight coordinate adjustment (~30m offset) to optimize stop-line placement
        target_lat = round(cand["lat"] + 0.00025, 6)
        target_lon = round(cand["lon"] + 0.00025, 6)
        issues.append({
            "issue_id": f"signal_relocate_{nid}",
            "type": "signal_placement",
            "subtype": "signal_relocate",
            "severity": "moderate",
            "description": (
                f"Signal at node {nid} ({sc}-way, {wt:.1f}s wait) experiences offset approach friction. "
                f"Relocating stop-line by ~30m to ({target_lat:.5f}, {target_lon:.5f}) "
                f"will eliminate approach blockage and improve green wave progression."
            ),
            "location": {"node_id": nid, "lat": cand["lat"], "lon": cand["lon"]},
            "metrics": {
                "node_id": nid,
                "street_count": sc,
                "avg_wait_time": wt,
                "conflict_rate": cr,
                "target_lat": target_lat,
                "target_lon": target_lon,
                "is_signal": True,
                "recommendation": "relocate_signal",
                "reason": "Optimize approach stop-line to relieve turning pocket bottleneck",
            },
        })

    log.info(
        f"Signal placement analysis: {len(issues)} recommendations ("
        f"{len(add_candidates[:8])} add, {len(remove_candidates[:4])} remove, "
        f"{len(relocate_candidates[:3])} relocate)"
    )
    return issues
