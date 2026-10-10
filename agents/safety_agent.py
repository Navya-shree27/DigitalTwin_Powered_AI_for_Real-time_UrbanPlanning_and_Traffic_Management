"""
agents/safety_agent.py
──────────────────────
Safety Assessment Agent.

Analyzes intersection conflict metrics, wait-time hazards, and spatial building
proximity constraints to flag traffic safety risks and physical limitation zones.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.multi_agent_framework import BaseAgent, OllamaClient

log = logging.getLogger("safety_agent")


class SafetyAssessmentAgent(BaseAgent):
    """
    Agent evaluating intersection conflict rates, near-miss hazards, and spatial widening constraints.
    """

    def __init__(self, client: OllamaClient | None = None):
        super().__init__(client=client, role_name="Safety Assessment Agent")

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Context expects:
          - telemetry: dict (with 'nodes' and 'edges')
          - safety_issues: list[dict]
        """
        telemetry = context.get("telemetry", {})
        nodes = telemetry.get("nodes", [])
        edges = telemetry.get("edges", [])

        # Filter high-risk nodes (conflict_rate > 1.0 or wait > 30s)
        high_risk_nodes = sorted(
            [n for n in nodes if n.get("conflict_rate", 0) > 0.8 or n.get("avg_wait_time", 0) > 30.0],
            key=lambda x: (x.get("conflict_rate", 0), x.get("avg_wait_time", 0)),
            reverse=True,
        )[:8]

        # Filter edges with building constraints (unwidenable)
        constrained_edges = [
            e for e in edges if e.get("widenable") is False and e.get("occupancy", 0) > 0.60
        ][:6]

        system_prompt = (
            "You are the Safety Assessment Agent in a Digital Twin Urban Traffic Management system. "
            "Your role is to assess intersection collision conflict risks, pedestrian/vehicle hazards, "
            "and spatial building constraints where road widening is physically impossible."
        )

        user_prompt = f"""
        Evaluate the following safety metrics and geometric constraints:

        === HIGH CONFLICT INTERSECTIONS ===
        {json.dumps([{
            'node_id': n.get('node_id'),
            'street_count': n.get('street_count'),
            'conflict_rate': f"{n.get('conflict_rate', 0):.2f} conflicts/hr",
            'avg_wait_time': f"{n.get('avg_wait_time', 0):.1f} s",
        } for n in high_risk_nodes], indent=2)}

        === SPATIALLY CONSTRAINED SATURATED CORRIDORS (Building Footprints Block Widening) ===
        {json.dumps([{
            'edge_id': e.get('edge_id'),
            'road_type': e.get('road_type'),
            'occupancy': f"{e.get('occupancy', 0):.1%}",
            'widenable': False
        } for e in constrained_edges], indent=2)}

        === TASK ===
        Provide your assessment formatted in JSON:
        {{
            "safety_status": "SECURE" | "MODERATE_RISK" | "HIGH_HAZARD",
            "safety_summary": "2-3 sentences overview",
            "critical_intersections": [
                {{"node_id": 123, "risk_type": "conflict/wait", "mitigation": "..."}}
            ],
            "spatial_constraint_warnings": [
                {{"edge_id": "...", "limitation": "..."}}
            ],
            "recommended_safety_actions": ["bullet 1", "bullet 2"]
        }}
        """

        def fallback(ctx: dict[str, Any]) -> dict[str, Any]:
            max_conflict = max([n.get("conflict_rate", 0) for n in high_risk_nodes], default=0.0)
            if max_conflict > 2.0 or len(high_risk_nodes) >= 4:
                status = "HIGH_HAZARD"
            elif max_conflict > 0.9 or len(high_risk_nodes) > 0:
                status = "MODERATE_RISK"
            else:
                status = "SECURE"

            crit_nodes = [
                {
                    "node_id": n.get("node_id"),
                    "risk_type": f"Elevated conflict rate ({n.get('conflict_rate', 0):.2f}/h) at {n.get('street_count', 3)}-way junction",
                    "mitigation": "Optimize signal phase split and introduce protected turning phases to eliminate crossing conflicts",
                }
                for n in high_risk_nodes[:5]
            ]

            warnings = [
                {
                    "edge_id": e.get("edge_id"),
                    "limitation": f"Building proximity restricts physical widening on {e.get('road_type', 'road')}. Must use transit/routing alternatives.",
                }
                for e in constrained_edges[:4]
            ]

            return {
                "safety_status": status,
                "safety_summary": (
                    f"Safety analysis identified {len(high_risk_nodes)} junctions with elevated vehicle conflict rates. "
                    f"Additionally, {len(constrained_edges)} congested segments are bounded by structural building footprints."
                ),
                "critical_intersections": crit_nodes,
                "spatial_constraint_warnings": warnings,
                "recommended_safety_actions": [
                    "Implement dedicated turning phases at high-conflict multi-branch junctions.",
                    "Enforce dynamic lane management and speed dampening on building-constrained residential/secondary corridors.",
                    "Deploy signal coordination across adjacent intersections to avoid queue spillback into conflict zones.",
                ],
            }

        return self._call_llm_or_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_func=fallback,
            context=context,
            format_json=True,
        )
