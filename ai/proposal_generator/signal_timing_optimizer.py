"""
ai/proposal_generator/signal_timing_optimizer.py
──────────────────────────────────────────────────────
Generates revised traffic-signal timing proposals for flagged intersections.

Algorithm
─────────
For each flagged congestion or intersection-safety issue that involves an
intersection node, it:
  1. Computes the total incoming flow to the intersection.
  2. Allocates green time proportionally to each approach (Webster's method).
  3. Produces a proposal with revised phase durations.

Webster's optimal cycle length formula:
  C_opt = (1.5 × L + 5) / (1 − Y)
  where L = lost time per cycle, Y = sum of critical flow ratios.

Each proposal output conforms to the ProposalRecord schema.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("signal_timing_optimizer")


def _make_proposal(
    proposal_id: str,
    issue_id: str,
    node_id: int,
    lat: float,
    lon: float,
    description: str,
    timing_plan: dict,
    expected_improvement: dict,
) -> dict:
    return {
        "proposal_id":          proposal_id,
        "type":                 "signal_timing",
        "issue_id":             issue_id,
        "location": {
            "node_id": node_id,
            "lat":     lat,
            "lon":     lon,
        },
        "description":          description,
        "parameters":           timing_plan,
        "expected_improvement": expected_improvement,
        "generated_at":         datetime.now(timezone.utc).isoformat(),
        "validated":            False,
    }


class SignalTimingOptimizer:
    """
    Generates Webster-method signal re-timing proposals for
    congestion and intersection-safety issues.
    """

    # Typical lost time per phase (seconds)
    LOST_TIME_PER_PHASE = 3.5
    # Saturation flow rate (vehicles / hour / lane)
    SATURATION_FLOW = 1800
    # Minimum / maximum green times (seconds)
    MIN_GREEN = 10
    MAX_GREEN = 90

    def generate(
        self,
        issues: list[dict],
        telemetry: dict,
    ) -> list[dict]:
        """
        Generate signal timing proposals for congestion / intersection issues.

        Parameters
        ──────────
        issues    : All detected issues (from all detectors).
        telemetry : Full simulation telemetry dict.

        Returns
        ───────
        List of ProposalRecord dicts.
        """
        # Build a lookup: node_id → node telemetry
        node_lookup = {n["node_id"]: n for n in telemetry.get("nodes", [])}
        # Build incoming flow map: node_id → list of (edge_flow, capacity)
        flow_map: dict[int, list[tuple[float, float]]] = {}
        for edge in telemetry.get("edges", []):
            v = edge["v"]
            flow_map.setdefault(v, []).append((edge["flow"], edge["capacity"]))

        proposals = []
        counter   = 0

        for issue in issues:
            itype = issue.get("type", "")
            if itype not in ("congestion", "intersection_safety"):
                continue

            # Try to extract node_id
            loc = issue.get("location", {})
            node_id = loc.get("node_id")
            if node_id is None:
                # congestion issue — use the destination node of the edge
                node_id = loc.get("node_v")
            if node_id is None:
                continue

            node_data = node_lookup.get(node_id, {})
            lat = node_data.get("lat", 0)
            lon = node_data.get("lon", 0)
            sc  = node_data.get("street_count", 2)

            if sc < 3:
                continue  # Not a proper signalized junction

            # Incoming flow ratios
            approaches = flow_map.get(node_id, [])
            if not approaches:
                approaches = [(400, 1200)] * max(sc - 1, 2)

            n_phases = max(2, min(sc - 1, 4))   # 2–4 phases
            L = self.LOST_TIME_PER_PHASE * n_phases  # total lost time per cycle

            # Critical flow ratios per phase (greedy assignment)
            sorted_approaches = sorted(approaches, key=lambda x: x[0] / max(x[1], 1), reverse=True)
            Y = sum(
                flow / max(cap, 1) / self.SATURATION_FLOW
                for flow, cap in sorted_approaches[:n_phases]
            )
            Y = min(Y, 0.95)  # avoid division by zero / over-saturation

            # Webster's optimal cycle length
            C_opt = (1.5 * L + 5) / max(1 - Y, 0.05)
            C_opt = max(40, min(C_opt, 180))   # practical bounds (40s–180s)

            # Effective green time
            G_eff = C_opt - L
            # Allocate proportionally to critical flow ratio
            flow_ratios = [f / max(c, 1) for f, c in sorted_approaches[:n_phases]]
            total_fr = max(sum(flow_ratios), 0.001)
            phases = []
            for i, fr in enumerate(flow_ratios):
                g = max(self.MIN_GREEN, min(self.MAX_GREEN, round(G_eff * fr / total_fr)))
                phases.append({
                    "phase": i + 1,
                    "green_s": g,
                    "amber_s": 3,
                    "red_s":   round(C_opt - g - 3),
                })

            timing_plan = {
                "cycle_length_s":     round(C_opt),
                "n_phases":           n_phases,
                "lost_time_s":        round(L),
                "effective_green_s":  round(G_eff),
                "phases":             phases,
                "method":             "Webster",
            }

            # Estimate improvement
            current_wait = node_data.get("avg_wait_time", 30)
            expected_wait_reduction_pct = min(30, round((Y / max(1, sc)) * 50))
            improvement = {
                "expected_wait_reduction_pct": expected_wait_reduction_pct,
                "expected_wait_s_after": round(current_wait * (1 - expected_wait_reduction_pct / 100)),
                "rationale": (
                    f"Webster-optimal cycle {round(C_opt)}s reduces over-saturation "
                    f"(Y={Y:.2f}) at this {sc}-phase junction."
                ),
            }

            counter += 1
            desc = (
                f"Retiming signal at node {node_id} (intersection, {sc} approaches). "
                f"Proposed cycle: {round(C_opt)}s with {n_phases} phases. "
                f"Expected wait reduction: ~{expected_wait_reduction_pct}%."
            )
            proposals.append(_make_proposal(
                proposal_id  = f"signal_{node_id}_{counter}",
                issue_id     = issue["issue_id"],
                node_id      = node_id,
                lat          = lat,
                lon          = lon,
                description  = desc,
                timing_plan  = timing_plan,
                expected_improvement = improvement,
            ))

        log.info(f"SignalTimingOptimizer: {len(proposals)} proposals generated.")
        return proposals


def generate_signal_proposals(issues: list[dict], telemetry: dict, **kwargs) -> list[dict]:
    return SignalTimingOptimizer(**kwargs).generate(issues, telemetry)
