"""
tests/test_agents.py
──────────────────────
Tests for the issue detection and proposal generation agents.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
import networkx as nx


def _make_test_telemetry():
    """Build minimal telemetry for agent tests."""
    G = nx.MultiDiGraph()
    for i in range(1, 6):
        G.add_node(i, x=75.92 + i*0.01, y=14.46 + i*0.01)
    G.add_edge(1, 2, length=500, speed_kph=40, capacity=1200, lanes=2, road_type="primary", travel_time=45)
    G.add_edge(2, 3, length=600, speed_kph=30, capacity=800,  lanes=1, road_type="secondary", travel_time=72)
    G.add_edge(3, 4, length=300, speed_kph=50, capacity=1800, lanes=3, road_type="motorway",  travel_time=21)
    G.add_edge(4, 5, length=700, speed_kph=20, capacity=600,  lanes=1, road_type="residential", travel_time=126)
    G.add_edge(5, 1, length=400, speed_kph=60, capacity=2000, lanes=4, road_type="motorway",  travel_time=24)

    from simulation.simulation_runner import SyntheticSimulator
    return SyntheticSimulator(G, duration_s=3600, seed=42).run()


class TestCongestionDetector:
    def test_returns_list(self):
        from agents.issue_detection.congestion_detector import detect_congestion
        tel = _make_test_telemetry()
        issues = detect_congestion(tel)
        assert isinstance(issues, list)

    def test_issue_schema(self):
        from agents.issue_detection.congestion_detector import detect_congestion
        tel = _make_test_telemetry()
        issues = detect_congestion(tel)
        for issue in issues:
            assert "issue_id" in issue
            assert issue["type"] == "congestion"
            assert issue["severity"] in ("severe", "moderate", "low")
            assert "location" in issue
            assert "metrics" in issue

    def test_sorted_by_severity(self):
        from agents.issue_detection.congestion_detector import detect_congestion
        tel = _make_test_telemetry()
        issues = detect_congestion(tel)
        priority = {"severe": 0, "moderate": 1, "low": 2}
        for i in range(len(issues) - 1):
            assert priority[issues[i]["severity"]] <= priority[issues[i+1]["severity"]]


class TestIntersectionSafetyAnalyzer:
    def test_returns_list(self):
        from agents.issue_detection.intersection_safety_analyzer import detect_unsafe_intersections
        tel = _make_test_telemetry()
        issues = detect_unsafe_intersections(tel)
        assert isinstance(issues, list)

    def test_issue_type_correct(self):
        from agents.issue_detection.intersection_safety_analyzer import detect_unsafe_intersections
        tel = _make_test_telemetry()
        for issue in detect_unsafe_intersections(tel):
            assert issue["type"] == "intersection_safety"


class TestLaneUtilizationAnalyzer:
    def test_returns_list(self):
        from agents.issue_detection.lane_utilization_analyzer import detect_lane_issues
        tel = _make_test_telemetry()
        issues = detect_lane_issues(tel)
        assert isinstance(issues, list)

    def test_subtypes_valid(self):
        from agents.issue_detection.lane_utilization_analyzer import detect_lane_issues
        tel = _make_test_telemetry()
        for issue in detect_lane_issues(tel):
            assert issue.get("subtype") in ("underutilized", "saturated")


class TestSignalTimingOptimizer:
    def test_generates_proposals(self):
        from agents.issue_detection.intersection_safety_analyzer import detect_unsafe_intersections
        from agents.issue_detection.congestion_detector import detect_congestion
        from agents.proposal_generator.signal_timing_optimizer import generate_signal_proposals
        tel = _make_test_telemetry()
        issues = detect_congestion(tel) + detect_unsafe_intersections(tel)
        proposals = generate_signal_proposals(issues, tel)
        assert isinstance(proposals, list)

    def test_proposal_schema(self):
        from agents.issue_detection.congestion_detector import detect_congestion
        from agents.proposal_generator.signal_timing_optimizer import generate_signal_proposals
        tel = _make_test_telemetry()
        issues = detect_congestion(tel)
        proposals = generate_signal_proposals(issues, tel)
        for p in proposals:
            assert p["type"] == "signal_timing"
            assert "parameters" in p
            assert "expected_improvement" in p
            assert "proposal_id" in p


class TestBeforeAfterComparator:
    def test_comparison_verdict(self):
        from validation.before_after_comparator import compare
        baseline = {
            "avg_travel_time_s": 60, "avg_wait_time_s": 30, "avg_speed_kph": 25,
            "congestion_ratio": 0.4, "total_delay_s": 1000, "emissions_proxy": 0.05,
            "efficiency_score": 50, "throughput_index": 0.6, "p85_travel_time_s": 90,
        }
        improved = {
            "avg_travel_time_s": 45, "avg_wait_time_s": 20, "avg_speed_kph": 35,
            "congestion_ratio": 0.2, "total_delay_s": 600, "emissions_proxy": 0.03,
            "efficiency_score": 70, "throughput_index": 0.75, "p85_travel_time_s": 65,
        }
        result = compare(baseline, improved, "test_proposal_1", scenario_id=1)
        assert result["verdict"] in ("APPROVED", "APPROVED_WITH_CONDITIONS", "REJECTED")
        assert "improvement_score" in result
        assert 0 <= result["improvement_score"] <= 100
        assert result["verdict"] == "APPROVED"   # all metrics improved
