"""
agents/orchestrator.py
──────────────────────
Multi-Agent Orchestrator.

Coordinates the end-to-end execution of:
  1. Traffic Analysis Agent
  2. Safety Assessment Agent
  3. Urban Planning & Optimization Agent

Synthesizes individual agent outputs, manages agent memory across analysis cycles,
and formats the final structured intelligence payload for the Digital Twin backend and dashboard.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from agents.city_inspector_agent.agent_memory import get_memory
from agents.multi_agent_framework import OllamaClient
from agents.planner_agent import UrbanPlanningAgent
from agents.safety_agent import SafetyAssessmentAgent
from agents.traffic_analysis_agent import TrafficAnalysisAgent

log = logging.getLogger("multi_agent_orchestrator")


class MultiAgentOrchestrator:
    """
    Coordinates and synthesizes the specialized multi-agent AI framework.
    """

    def __init__(
        self,
        ollama_host: str | None = None,
        ollama_model: str | None = None,
    ):
        self.client = OllamaClient(host=ollama_host, model=ollama_model)
        self.traffic_agent = TrafficAnalysisAgent(client=self.client)
        self.safety_agent = SafetyAssessmentAgent(client=self.client)
        self.planner_agent = UrbanPlanningAgent(client=self.client)
        self.memory = get_memory()

    def run_pipeline(
        self,
        scenario_id: int,
        scenario_name: str,
        telemetry: dict[str, Any],
        issues: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Execute full multi-agent collaborative cycle.
        """
        log.info(f"Orchestrator starting multi-agent cycle for scenario {scenario_id} ('{scenario_name}')...")

        context = {
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "telemetry": telemetry,
            "issues": issues,
            "prior_summary": self.memory.get_prior_summary(scenario_id),
        }

        # Step 1: Traffic Analysis Agent
        log.info("Running Traffic Analysis Agent...")
        traffic_result = self.traffic_agent.run(context)
        context["traffic_analysis"] = traffic_result

        # Step 2: Safety Assessment Agent
        log.info("Running Safety Assessment Agent...")
        safety_result = self.safety_agent.run(context)
        context["safety_analysis"] = safety_result

        # Step 3: Planner / Optimization Agent
        log.info("Running Urban Planning Agent...")
        planner_result = self.planner_agent.run(context)
        context["planner_analysis"] = planner_result

        # Step 4: Final Synthesis Narrative
        narrative = self._synthesize_narrative(
            scenario_name=scenario_name,
            traffic_res=traffic_result,
            safety_res=safety_result,
            planner_res=planner_result,
            summary=telemetry.get("summary", {}),
        )

        # Step 5: Multi-Candidate Evaluation & Selection
        proposals = planner_result.get("proposals", [])
        recommended_intervention, evaluated_candidates = self.evaluate_candidates(
            scenario_id=scenario_id,
            baseline_telemetry=telemetry,
            proposals=proposals,
            traffic_res=traffic_result,
            safety_res=safety_result,
            planner_res=planner_result,
            max_candidates=6,
        )

        # Step 6: Update Agent Memory
        summary_obj = telemetry.get("summary", {})
        severe_count = sum(1 for i in issues if i.get("severity") == "severe")
        memory_entry = self.memory.record(
            scenario_id=scenario_id,
            summary=narrative[:300] + ("…" if len(narrative) > 300 else ""),
            key_metrics={
                "avg_speed_kph": summary_obj.get("avg_speed_kph", 0),
                "avg_travel_time_s": summary_obj.get("avg_travel_time_s", 0),
                "congestion_ratio": summary_obj.get("congestion_ratio", 0),
                "severe_issues": severe_count,
            },
        )

        # Filter top issues and recommendations
        priority = {"severe": 0, "moderate": 1, "low": 2}
        top_issues = sorted(issues, key=lambda x: priority.get(x.get("severity"), 3))[:6]

        recommendations = [
            p.get("description") for p in proposals[:6]
        ]

        result_payload = {
            "orchestrator_timestamp": datetime.now(timezone.utc).isoformat(),
            "recommended_intervention": recommended_intervention,
            "evaluated_candidates": evaluated_candidates,
            "narrative": narrative,
            "traffic_analysis": traffic_result,
            "safety_analysis": safety_result,
            "planning_strategy": planner_result.get("planning_strategy", {}),
            "proposals": proposals,
            "top_issues": top_issues,
            "recommendations": recommendations,
            "model": self.client.model if self.client.is_available() else "multi-agent-analytical-engine",
            "memory_cycle": memory_entry.get("cycle", 1),
        }

        log.info(f"Multi-agent cycle completed for scenario {scenario_id}.")
        return result_payload

    def standardize_intervention(self, p: dict[str, Any]) -> dict[str, Any]:
        """
        Guarantees standardized schema for any candidate proposal dict:
          - intervention_type: 'signal_timing' | 'lane_change' | 'route_diversion' | 'infrastructure'
          - target_edge: str | None
          - target_node: int | None
          - reason: str
          - parameters: dict
          - expected_effect: str
        """
        ptype = p.get("type") or p.get("intervention_type") or "infrastructure"
        if ptype not in ("signal_timing", "lane_change", "route_diversion", "infrastructure"):
            ptype = "infrastructure"

        loc = p.get("location", {}) if isinstance(p.get("location"), dict) else {}
        params = p.get("parameters", {}).copy() if isinstance(p.get("parameters"), dict) else {}

        target_edge = loc.get("edge_id") or loc.get("edge") or params.get("target_edge") or params.get("edge_id") or params.get("edge")
        target_node = loc.get("node_id") or params.get("target_node") or params.get("node_id")
        if target_node is not None:
            try:
                target_node = int(target_node)
            except (ValueError, TypeError):
                target_node = None

        imp = p.get("expected_improvement", {})
        if isinstance(imp, dict):
            expected_effect = imp.get("rationale") or f"Expected wait reduction of ~{imp.get('expected_wait_reduction_pct', 20)}%."
        else:
            expected_effect = str(imp)

        reason = (
            p.get("description")
            or f"AI optimization identified priority {ptype} intervention to alleviate network bottleneck."
        )

        params["type"] = ptype
        if target_edge:
            params["target_edge"] = str(target_edge)
            params["edge_id"] = str(target_edge)
        if target_node:
            params["target_node"] = target_node
            params["node_id"] = target_node

        return {
            "intervention_type": ptype,
            "target_edge": str(target_edge) if target_edge else None,
            "target_node": target_node,
            "reason": reason,
            "parameters": params,
            "expected_effect": expected_effect,
        }

    def evaluate_candidates(
        self,
        scenario_id: int,
        baseline_telemetry: dict[str, Any],
        proposals: list[dict[str, Any]],
        traffic_res: dict[str, Any] | None = None,
        safety_res: dict[str, Any] | None = None,
        planner_res: dict[str, Any] | None = None,
        max_candidates: int = 6,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """
        Evaluate multiple candidate interventions by independently re-simulating
        each candidate on the Digital Twin and selecting the best performing one.
        """
        if not proposals:
            fallback = {
                "intervention_type": "infrastructure",
                "target_edge": None,
                "target_node": None,
                "reason": "General network-wide demand management and capacity monitoring.",
                "parameters": {"action": "ADAPTIVE_CORRIDOR_MONITORING"},
                "expected_effect": "Maintain current Level of Service across key arterial segments.",
            }
            return fallback, []

        from simulation.simulation_runner import run_simulation
        from validation.before_after_comparator import compare
        from validation.metrics_calculator import compute_metrics

        baseline_kpis = compute_metrics(baseline_telemetry)

        # Assemble diverse candidate pool across intervention types
        candidate_pool: list[dict[str, Any]] = []
        sig_cands = [p for p in proposals if p.get("type") == "signal_timing"][:2]
        lane_cands = [p for p in proposals if p.get("type") == "lane_change"][:2]
        div_cands = [p for p in proposals if p.get("type") == "route_diversion"][:2]

        candidate_pool.extend(sig_cands)
        candidate_pool.extend(lane_cands)
        candidate_pool.extend(div_cands)

        # If still room, fill with remaining proposals
        for p in proposals:
            if len(candidate_pool) >= max_candidates:
                break
            if p not in candidate_pool:
                candidate_pool.append(p)

        evaluated: list[dict[str, Any]] = []
        for idx, cand in enumerate(candidate_pool):
            std_cand = self.standardize_intervention(cand)
            cand_id = cand.get("proposal_id", f"cand_{idx+1}")

            try:
                cand_tel = run_simulation(
                    scenario_id=scenario_id,
                    engine="synthetic",
                    duration_s=baseline_telemetry.get("duration_s", 3600),
                    seed=baseline_telemetry.get("seed", 42),
                    apply_proposals=[std_cand],
                )
                cand_kpis = compute_metrics(cand_tel)
                comparison = compare(
                    baseline_metrics=baseline_kpis,
                    proposal_metrics=cand_kpis,
                    proposal_id=cand_id,
                    scenario_id=scenario_id,
                )
                imp_score = comparison.get("improvement_score", 0.0)
                verdict = comparison.get("verdict", "REJECTED")
                improved_count = sum(1 for m in comparison.get("metrics", {}).values() if m.get("improved"))
                delay_delta = comparison.get("metrics", {}).get("total_delay_s", {}).get("delta", 0.0)

                evaluated.append({
                    "candidate_id": cand_id,
                    "intervention_type": std_cand["intervention_type"],
                    "description": std_cand["reason"],
                    "improvement_score": imp_score,
                    "verdict": verdict,
                    "improved_kpis_count": improved_count,
                    "delay_delta_s": delay_delta,
                    "intervention": std_cand,
                    "comparison": comparison,
                })
            except Exception as e:
                log.warning(f"Evaluation failed for candidate {cand_id}: {e}")

        if not evaluated:
            primary = self.standardize_intervention(proposals[0])
            return primary, []

        # Rank candidates: highest improvement score -> highest improved KPI count -> greatest delay reduction
        ranked = sorted(
            evaluated,
            key=lambda c: (
                c["improvement_score"],
                c["improved_kpis_count"],
                -c["delay_delta_s"],
            ),
            reverse=True,
        )

        best_candidate = ranked[0]
        return best_candidate["intervention"], evaluated


    def _synthesize_narrative(
        self,
        scenario_name: str,
        traffic_res: dict[str, Any],
        safety_res: dict[str, Any],
        planner_res: dict[str, Any],
        summary: dict[str, Any],
    ) -> str:
        """Combine agent outputs into a clear, unified executive briefing."""
        t_exec = traffic_res.get("executive_summary", "")
        s_exec = safety_res.get("safety_summary", "")
        p_strat = planner_res.get("planning_strategy", {})
        p_impact = p_strat.get("expected_network_impact", "") if isinstance(p_strat, dict) else ""

        lines = [
            f"=== MULTI-AGENT DIGITAL TWIN TRAFFIC INTELLIGENCE BRIEFING ===",
            f"Scenario: {scenario_name}",
            f"Network Health Status: {traffic_res.get('health_status', 'ASSESSED')} | Safety Risk Level: {safety_res.get('safety_status', 'EVALUATED')}",
            f"",
            f"1. TRAFFIC DIAGNOSTICS & ML ASSESSMENT:",
            f"   • {t_exec}",
            f"   • {traffic_res.get('ml_interpretation', 'ML model identified key congestion drivers.')}",
            f"",
            f"2. SAFETY & SPATIAL FEASIBILITY:",
            f"   • {s_exec}",
            f"",
            f"3. STRATEGIC INTERVENTIONS & OPTIMIZATION:",
            f"   • Generated {len(planner_res.get('proposals', []))} actionable interventions across signal timing, lane management, and route diversions.",
            f"   • {p_impact}",
            f"",
            f"4. KEY ACTION ITEMS FOR CITY PLANNERS:",
        ]

        if isinstance(p_strat, dict) and "priority_tier_1" in p_strat:
            for item in p_strat["priority_tier_1"][:4]:
                lines.append(f"   → {item}")

        return "\n".join(lines)


# Global orchestrator singleton
_orchestrator: MultiAgentOrchestrator | None = None


def get_orchestrator() -> MultiAgentOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MultiAgentOrchestrator()
    return _orchestrator
