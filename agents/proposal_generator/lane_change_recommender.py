"""
agents/proposal_generator/lane_change_recommender.py
──────────────────────────────────────────────────────
Recommends lane reconfigurations for over/under-utilized edges.

Proposals generated
───────────────────
  • ADD_LANE    : for severely saturated edges where adding a lane is feasible
  • REMOVE_LANE : for underutilized edges where lanes can be reclaimed
  • REVERSIBLE  : for moderate saturation on bidirectional roads (tidal flow)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger("lane_change_recommender")


def _make_proposal(proposal_id, issue_id, edge_id, u, v, subtype, description, parameters, improvement):
    return {
        "proposal_id":          proposal_id,
        "type":                 "lane_change",
        "subtype":              subtype,
        "issue_id":             issue_id,
        "location": {
            "edge_id": edge_id,
            "node_u":  u,
            "node_v":  v,
        },
        "description":          description,
        "parameters":           parameters,
        "expected_improvement": improvement,
        "generated_at":         datetime.now(timezone.utc).isoformat(),
        "validated":            False,
    }


class LaneChangeRecommender:
    """Generate lane reconfiguration proposals from lane utilization issues."""

    def generate(self, issues: list[dict], telemetry: dict) -> list[dict]:
        edge_lookup = {e["edge_id"]: e for e in telemetry.get("edges", [])}
        proposals = []
        counter = 0

        for issue in issues:
            if issue.get("type") != "lane_utilization":
                continue

            loc      = issue.get("location", {})
            edge_id  = loc.get("edge_id", "")
            u        = loc.get("node_u", 0)
            v        = loc.get("node_v", 0)
            subtype  = issue.get("subtype", "")
            severity = issue.get("severity", "low")
            edge     = edge_lookup.get(edge_id, {})
            lanes    = edge.get("lanes", 1)
            occupancy = edge.get("occupancy", 0)
            capacity  = edge.get("capacity", 800)
            road_type = edge.get("road_type", "road")

            widenable = edge.get("widenable", True)

            if subtype == "saturated" and lanes < 4:
                if widenable:
                    new_lanes = lanes + 1
                    counter += 1
                    params = {
                        "edge": edge_id,
                        "type": "lane_change",
                        "current_lanes": lanes,
                        "new_lanes":     new_lanes,
                        "action":        "ADD_LANE",
                    }
                    improvement = {
                        "expected_capacity_increase_pct": round(100 / lanes),
                        "expected_occupancy_after":        round(occupancy * lanes / new_lanes, 4),
                        "rationale": f"Adding 1 lane increases capacity by {round(100/lanes)}%.",
                    }
                    desc = (
                        f"Add 1 lane to {road_type} edge {edge_id} "
                        f"(currently {lanes} lanes, occupancy {occupancy:.1%}). "
                        f"Expected capacity increase: {round(100/lanes)}%."
                    )
                    proposals.append(_make_proposal(
                        f"lane_add_{edge_id}_{counter}",
                        issue["issue_id"],
                        edge_id, u, v,
                        "ADD_LANE", desc, params, improvement,
                    ))
                else:
                    # NOT widenable due to building constraints. Propose lane repurposing/dynamic flow
                    counter += 1
                    params = {
                        "edge": edge_id,
                        "type": "lane_change",
                        "current_lanes": lanes,
                        "action":        "REPURPOSE_LANE",
                        "details":       "Tidal flow / Transit lane priority",
                    }
                    improvement = {
                        "expected_capacity_increase_pct": 15,
                        "rationale": "Optimizes existing space without physical road expansion (restricted by buildings).",
                    }
                    desc = (
                        f"Implement dynamic lane control / bus priority lane on {road_type} edge {edge_id}. "
                        f"Physical road widening is restricted by building proximity. "
                        f"Optimizes existing {lanes} lanes."
                    )
                    proposals.append(_make_proposal(
                        f"lane_repurpose_{edge_id}_{counter}",
                        issue["issue_id"],
                        edge_id, u, v,
                        "REPURPOSE_LANE", desc, params, improvement,
                    ))

            elif subtype == "underutilized" and lanes >= 2:
                new_lanes = lanes - 1
                counter += 1
                params = {
                    "edge": edge_id,
                    "type": "lane_change",
                    "current_lanes": lanes,
                    "new_lanes":     new_lanes,
                    "action":        "REMOVE_LANE",
                    "repurpose_suggestion": "cycle lane / parking / green buffer",
                }
                improvement = {
                    "freed_lanes": 1,
                    "expected_occupancy_after": round(occupancy * lanes / new_lanes, 4),
                    "rationale": f"Removing 1 lane from underutilized road frees space for other uses.",
                }
                desc = (
                    f"Remove 1 lane from {road_type} edge {edge_id} "
                    f"({lanes} lanes, only {occupancy:.1%} occupancy). "
                    f"Freed lane can be repurposed."
                )
                proposals.append(_make_proposal(
                    f"lane_remove_{edge_id}_{counter}",
                    issue["issue_id"],
                    edge_id, u, v,
                    "REMOVE_LANE", desc, params, improvement,
                ))

        log.info(f"LaneChangeRecommender: {len(proposals)} proposals generated.")
        return proposals


def generate_lane_proposals(issues: list[dict], telemetry: dict) -> list[dict]:
    return LaneChangeRecommender().generate(issues, telemetry)
