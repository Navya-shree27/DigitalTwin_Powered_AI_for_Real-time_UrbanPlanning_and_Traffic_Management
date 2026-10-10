"""
tests/test_intervention_loop.py
───────────────────────────────
End-to-End Closed-Loop AI Decision-Making and Intervention Validation Test.

Exercises the complete 12-step cycle:
  1. Run baseline Digital Twin simulation.
  2. Verify ML predictions exist on simulated edges (ml_congestion_level, ml_risk_score, etc.).
  3. Run Traffic Analysis Agent.
  4. Run Safety Assessment Agent.
  5. Run Urban Planning Agent.
  6. Run Multi-Agent Orchestrator.
  7. Extract structured `recommended_intervention`.
  8. Apply recommended intervention to the Digital Twin.
  9. Run simulation again with intervention applied.
 10. Compare baseline vs proposal metrics using before_after_comparator.
 11. Verify all 9 KPI results exist.
 12. Verify a valid verdict is returned.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from agents.issue_detection.congestion_detector import detect_congestion
from agents.issue_detection.intersection_safety_analyzer import detect_unsafe_intersections
from agents.issue_detection.lane_utilization_analyzer import detect_lane_issues
from agents.orchestrator import MultiAgentOrchestrator
from agents.planner_agent import UrbanPlanningAgent
from agents.safety_agent import SafetyAssessmentAgent
from agents.traffic_analysis_agent import TrafficAnalysisAgent
from simulation.simulation_runner import run_simulation
from validation.before_after_comparator import compare
from validation.metrics_calculator import compute_metrics


class TestInterventionLoop:
    def test_complete_end_to_end_intervention_cycle(self):
        # ── Step 1: Run baseline Digital Twin simulation ─────────────────────────
        scenario_id = 1
        baseline_tel = run_simulation(
            scenario_id=scenario_id,
            engine="synthetic",
            duration_s=3600,
            seed=42,
        )
        assert baseline_tel is not None
        assert "edges" in baseline_tel and "nodes" in baseline_tel
        assert len(baseline_tel["edges"]) > 0

        # ── Step 2: Verify ML predictions exist on edges ─────────────────────────
        sample_edge = baseline_tel["edges"][0]
        assert "ml_congestion_level" in sample_edge, "Edge missing ml_congestion_level"
        assert "ml_congestion_label" in sample_edge, "Edge missing ml_congestion_label"
        assert "ml_congestion_probs" in sample_edge, "Edge missing ml_congestion_probs"
        assert "ml_risk_score" in sample_edge, "Edge missing ml_risk_score"
        assert 0.0 <= sample_edge["ml_risk_score"] <= 1.0

        # Compute baseline KPIs
        baseline_metrics = compute_metrics(baseline_tel)
        assert baseline_metrics["avg_speed_kph"] > 0
        assert baseline_metrics["avg_travel_time_s"] > 0
        assert baseline_metrics["efficiency_score"] >= 0

        # Issue detection
        issues = (
            detect_congestion(baseline_tel)
            + detect_unsafe_intersections(baseline_tel)
            + detect_lane_issues(baseline_tel)
        )
        assert len(issues) > 0, "No issues detected in baseline simulation"

        # ── Step 3: Run Traffic Analysis Agent ──────────────────────────────────
        context = {
            "scenario_id": scenario_id,
            "scenario_name": "Davanagere City Center Peak",
            "telemetry": baseline_tel,
            "issues": issues,
        }
        traffic_agent = TrafficAnalysisAgent()
        traffic_res = traffic_agent.run(context)
        assert "health_status" in traffic_res
        assert "executive_summary" in traffic_res
        assert "top_bottlenecks" in traffic_res
        context["traffic_analysis"] = traffic_res

        # ── Step 4: Run Safety Assessment Agent ─────────────────────────────────
        safety_agent = SafetyAssessmentAgent()
        safety_res = safety_agent.run(context)
        assert "safety_status" in safety_res
        assert "safety_summary" in safety_res
        assert "critical_intersections" in safety_res
        context["safety_analysis"] = safety_res

        # ── Step 5: Run Urban Planning Agent ────────────────────────────────────
        planner_agent = UrbanPlanningAgent()
        planner_res = planner_agent.run(context)
        assert "proposals" in planner_res
        assert "planning_strategy" in planner_res
        assert len(planner_res["proposals"]) > 0
        context["planner_analysis"] = planner_res

        # ── Step 6: Run Multi-Agent Orchestrator ────────────────────────────────
        orchestrator = MultiAgentOrchestrator()
        orchestration_result = orchestrator.run_pipeline(
            scenario_id=scenario_id,
            scenario_name="Davanagere City Center Peak",
            telemetry=baseline_tel,
            issues=issues,
        )

        assert "narrative" in orchestration_result
        assert "proposals" in orchestration_result
        assert "recommended_intervention" in orchestration_result

        # ── Step 7: Extract structured recommended_intervention ─────────────────
        rec_intervention = orchestration_result["recommended_intervention"]
        assert isinstance(rec_intervention, dict)
        assert "intervention_type" in rec_intervention
        assert rec_intervention["intervention_type"] in (
            "signal_timing",
            "lane_change",
            "route_diversion",
            "infrastructure",
        )
        assert "reason" in rec_intervention
        assert "parameters" in rec_intervention
        assert "expected_effect" in rec_intervention

        # ── Step 8 & 9: Apply intervention to Digital Twin & re-simulate ────────
        prop_tel = run_simulation(
            scenario_id=scenario_id,
            engine="synthetic",
            duration_s=3600,
            seed=42,
            apply_proposals=[rec_intervention],
        )
        assert prop_tel is not None
        assert len(prop_tel["edges"]) == len(baseline_tel["edges"])

        # Compute proposal KPIs
        proposal_metrics = compute_metrics(prop_tel)

        # ── Step 10: Compare baseline vs proposal metrics ────────────────────────
        comparison = compare(
            baseline_metrics=baseline_metrics,
            proposal_metrics=proposal_metrics,
            proposal_id=rec_intervention.get("parameters", {}).get("proposal_id", "rec_intervention_1"),
            scenario_id=scenario_id,
        )

        # ── Step 11: Verify all 9 KPI results exist ──────────────────────────────
        expected_kpis = [
            "avg_travel_time_s",
            "avg_wait_time_s",
            "avg_speed_kph",
            "congestion_ratio",
            "total_delay_s",
            "emissions_proxy",
            "efficiency_score",
            "throughput_index",
            "p85_travel_time_s",
        ]
        diff_metrics = comparison.get("metrics", {})
        for kpi in expected_kpis:
            assert kpi in diff_metrics, f"Missing KPI {kpi} in comparison"
            kpi_data = diff_metrics[kpi]
            assert "before" in kpi_data
            assert "after" in kpi_data
            assert "delta" in kpi_data
            assert "delta_pct" in kpi_data
            assert "improved" in kpi_data

        # ── Step 12: Verify a valid verdict is returned ─────────────────────────
        assert comparison["verdict"] in ("APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED")
        assert 0.0 <= comparison["improvement_score"] <= 100.0
        assert len(comparison["summary"]) > 10

    def test_multi_candidate_evaluation_and_selection(self):
        """
        Verify that the Orchestrator evaluates multiple candidate proposals
        across intervention types (signal timing, lane changes, route diversions)
        and selects the top-performing candidate based on real simulated KPIs.
        """
        scenario_id = 1
        baseline_tel = run_simulation(
            scenario_id=scenario_id,
            engine="synthetic",
            duration_s=3600,
            seed=42,
        )
        issues = (
            detect_congestion(baseline_tel)
            + detect_unsafe_intersections(baseline_tel)
            + detect_lane_issues(baseline_tel)
        )

        planner = UrbanPlanningAgent()
        planner_res = planner.run({"telemetry": baseline_tel, "issues": issues})
        proposals = planner_res.get("proposals", [])
        assert len(proposals) > 0

        orchestrator = MultiAgentOrchestrator()
        best_intervention, evaluated_candidates = orchestrator.evaluate_candidates(
            scenario_id=scenario_id,
            baseline_telemetry=baseline_tel,
            proposals=proposals,
            max_candidates=6,
        )

        assert isinstance(best_intervention, dict)
        assert best_intervention["intervention_type"] in (
            "signal_timing",
            "lane_change",
            "route_diversion",
            "infrastructure",
        )
        assert len(evaluated_candidates) > 0

        # Verify candidate evaluation contents
        for cand in evaluated_candidates:
            assert "candidate_id" in cand
            assert "intervention_type" in cand
            assert "improvement_score" in cand
            assert "verdict" in cand
            assert "comparison" in cand
            assert "metrics" in cand["comparison"]
            assert cand["verdict"] in ("APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED")

        # Verify best candidate matches top ranked candidate
        top_cand = evaluated_candidates[0]
        assert best_intervention["reason"] == top_cand["intervention"]["reason"]

