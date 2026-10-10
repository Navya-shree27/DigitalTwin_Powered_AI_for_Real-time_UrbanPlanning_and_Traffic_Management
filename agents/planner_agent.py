"""
agents/planner_agent.py
───────────────────────
Urban Planning & Optimization Agent.

Synthesizes traffic bottlenecks and safety constraints into prioritized,
actionable engineering interventions:
  1. Signal timing optimization (Webster's method).
  2. Route diversion schemes (k-shortest path detours).
  3. Lane reconfiguration (physical additions vs. dynamic transit repurposing).
  4. Urban infrastructure enhancements.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.multi_agent_framework import BaseAgent, OllamaClient
from agents.proposal_generator.lane_change_recommender import generate_lane_proposals
from agents.proposal_generator.route_diversion_planner import generate_diversion_proposals
from agents.proposal_generator.signal_timing_optimizer import generate_signal_proposals

log = logging.getLogger("planner_agent")


class UrbanPlanningAgent(BaseAgent):
    """
    Agent responsible for generating actionable urban planning and traffic management proposals.
    """

    def __init__(self, client: OllamaClient | None = None):
        super().__init__(client=client, role_name="Urban Planning & Optimization Agent")

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Context expects:
          - telemetry: dict
          - issues: list[dict]
          - traffic_analysis: dict
          - safety_analysis: dict
        """
        telemetry = context.get("telemetry", {})
        issues = context.get("issues", [])

        # Generate rule/algorithmic proposals
        signal_proposals = generate_signal_proposals(issues, telemetry)
        lane_proposals = generate_lane_proposals(issues, telemetry)
        diversion_proposals = generate_diversion_proposals(issues, telemetry)

        all_proposals = signal_proposals + lane_proposals + diversion_proposals

        system_prompt = (
            "You are the Urban Planning & Optimization Agent in a Digital Twin Urban Traffic Management system. "
            "Your role is to formulate high-impact, practical traffic engineering interventions (signal retiming, "
            "route diversions, lane repurposing, transit priority) and rank them by return-on-investment."
        )

        user_prompt = f"""
        Review the following generated candidate interventions and context:

        === CANDIDATE PROPOSALS SUMMARY ===
        Total Signal Timing Proposals: {len(signal_proposals)}
        Total Lane Configuration Proposals: {len(lane_proposals)}
        Total Route Diversion Proposals: {len(diversion_proposals)}

        === TOP INTERVENTIONS ===
        {json.dumps([{
            'proposal_id': p.get('proposal_id'),
            'type': p.get('type'),
            'description': p.get('description'),
            'expected_improvement': p.get('expected_improvement'),
        } for p in all_proposals[:8]], indent=2)}

        === TASK ===
        Provide your strategic planning recommendations in JSON:
        {{
            "strategy_title": "Strategic Optimization Plan",
            "priority_tier_1": ["top action 1", "top action 2"],
            "expected_network_impact": "Expected reduction in delays and bottlenecks",
            "policy_recommendations": ["policy 1", "policy 2"]
        }}
        """

        def fallback(ctx: dict[str, Any]) -> dict[str, Any]:
            top_actions = [p.get("description", "") for p in all_proposals[:4]]
            return {
                "strategy_title": "Multi-Modal Corridor & Junction Optimization Strategy",
                "priority_tier_1": top_actions or ["Deploy Webster-optimal signal timings at key junctions."],
                "expected_network_impact": (
                    f"Implementing top {min(len(all_proposals), 5)} interventions is projected to yield a "
                    "15-30% reduction in intersection wait times and reduce bottleneck occupancy below saturation."
                ),
                "policy_recommendations": [
                    "Prioritize adaptive signal timing over static phase plans during peak hours.",
                    "Implement dynamic route navigation guidance at perimeter corridors to divert demand.",
                    "Adopt dedicated bus transit priority on unwidenable arterial corridors.",
                ],
            }

        planning_narrative = self._call_llm_or_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_func=fallback,
            context=context,
            format_json=True,
        )

        return {
            "proposals": all_proposals,
            "signal_proposals": signal_proposals,
            "lane_proposals": lane_proposals,
            "diversion_proposals": diversion_proposals,
            "planning_strategy": planning_narrative,
        }
