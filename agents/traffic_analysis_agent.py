"""
agents/traffic_analysis_agent.py
────────────────────────────────
Traffic Analysis Agent.

Consumes structured ML predictions and edge-level simulation telemetry to:
  - Interpret ML-predicted congestion states and probability distributions.
  - Identify critical bottleneck corridors and network congestion spread.
  - Formulate structured diagnostic findings for downstream agents.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.multi_agent_framework import BaseAgent, OllamaClient

log = logging.getLogger("traffic_analysis_agent")


class TrafficAnalysisAgent(BaseAgent):
    """
    Agent responsible for deep traffic flow diagnostics and ML model interpretation.
    """

    def __init__(self, client: OllamaClient | None = None):
        super().__init__(client=client, role_name="Traffic Analysis Agent")

    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Context expects:
          - telemetry: dict (with 'summary' and ML-enriched 'edges')
          - scenario_name: str
        """
        telemetry = context.get("telemetry", {})
        edges = telemetry.get("edges", [])
        summary = telemetry.get("summary", {})

        # Identify top ML-predicted high-risk bottlenecks
        congested_edges = sorted(
            [e for e in edges if e.get("ml_congestion_level", 0) >= 1 or e.get("occupancy", 0) > 0.55],
            key=lambda x: (x.get("ml_risk_score", 0), x.get("occupancy", 0)),
            reverse=True,
        )[:8]

        system_prompt = (
            "You are the Traffic Analysis Agent in a Digital Twin Urban Traffic Management system. "
            "Your role is to interpret trained Machine Learning predictions, assess road network congestion, "
            "and diagnose systemic traffic bottlenecks. Be concise, authoritative, and data-grounded."
        )

        user_prompt = f"""
        Analyze the following traffic telemetry and ML model predictions:

        === NETWORK TELEMETRY SUMMARY ===
        Scenario: {context.get('scenario_name', 'Urban Baseline')}
        Average Speed: {summary.get('avg_speed_kph', 0):.1f} km/h
        Average Wait Time: {summary.get('avg_wait_time_s', 0):.1f} s
        Congestion Ratio: {summary.get('congestion_ratio', 0):.1%}
        Total Flow: {summary.get('total_flow_veh_h', 0):.0f} veh/h

        === TOP ML-FLAGGED CONGESTION HOTSPOTS ===
        {json.dumps([{
            'edge_id': e.get('edge_id'),
            'road_type': e.get('road_type'),
            'occupancy': f"{e.get('occupancy', 0):.1%}",
            'speed_sim': f"{e.get('speed_sim', 0):.1f} km/h",
            'ml_prediction': e.get('ml_congestion_label', 'Unknown'),
            'ml_risk_score': e.get('ml_risk_score', 0),
            'ml_probabilities': e.get('ml_congestion_probs', {})
        } for e in congested_edges], indent=2)}

        === TASK ===
        Provide your assessment formatted in JSON with the following structure:
        {{
            "health_status": "OPTIMAL" | "MODERATE_CONGESTION" | "CRITICAL_BOTTLENECK",
            "executive_summary": "2-3 sentences overview",
            "ml_interpretation": "Explanation of ML predictions and probability risk factors",
            "top_bottlenecks": [
                {{"edge_id": "...", "severity": "severe/moderate", "cause": "..."}}
            ],
            "key_observations": ["bullet 1", "bullet 2", "bullet 3"]
        }}
        """

        def fallback(ctx: dict[str, Any]) -> dict[str, Any]:
            cong_ratio = summary.get("congestion_ratio", 0)
            if cong_ratio > 0.25 or len([e for e in congested_edges if e.get("ml_congestion_level") == 2]) > 0:
                status = "CRITICAL_BOTTLENECK"
            elif cong_ratio > 0.10:
                status = "MODERATE_CONGESTION"
            else:
                status = "OPTIMAL"

            bottlenecks = [
                {
                    "edge_id": e.get("edge_id"),
                    "severity": e.get("ml_congestion_label", "Moderate").lower(),
                    "cause": f"Volume-to-capacity ratio {e.get('occupancy', 0):.1%} exceeds throughput threshold on {e.get('road_type', 'road')}",
                    "ml_confidence": e.get("ml_risk_score", 0.7),
                }
                for e in congested_edges[:5]
            ]

            return {
                "health_status": status,
                "executive_summary": (
                    f"Network exhibits {status.replace('_', ' ').lower()} with an average speed of "
                    f"{summary.get('avg_speed_kph', 0):.1f} km/h and {summary.get('congestion_ratio', 0):.1%} "
                    f"of edges operating near or above saturation capacity."
                ),
                "ml_interpretation": (
                    f"The trained Random Forest model flagged {len(congested_edges)} critical segments. "
                    "Primary drivers identified by feature importance are volume-to-capacity occupancy and speed degradation ratio."
                ),
                "top_bottlenecks": bottlenecks,
                "key_observations": [
                    f"Overall network congestion ratio is currently {summary.get('congestion_ratio', 0):.1%}.",
                    f"Average vehicle wait time stands at {summary.get('avg_wait_time_s', 0):.1f} seconds across active corridors.",
                    f"Identified {len(congested_edges)} segments requiring priority optimization intervention.",
                ],
            }

        return self._call_llm_or_fallback(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            fallback_func=fallback,
            context=context,
            format_json=True,
        )
