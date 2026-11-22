"""
tests/test_signal_planning.py
───────────────────────────────
Unit tests for signal addition/removal analyzer, signal placement proposer,
and per-intersection simulator.
"""
import pytest
from ai.issue_detection.signal_placement_analyzer import detect_signal_placement_issues
from ai.proposal_generator.signal_placement_proposer import generate_signal_placement_proposals
from simulation.intersection_simulator import simulate_intersection


def test_signal_placement_analyzer_detects_add():
    telemetry = {
        "nodes": [
            {
                "node_id": "101",
                "street_count": 4,
                "conflict_rate": 0.35,
                "wait_time_s": 25.0,
                "highway": "priority",
                "lat": 14.464,
                "lon": 75.921,
            }
        ]
    }
    issues = detect_signal_placement_issues(telemetry)
    assert len(issues) == 1
    assert issues[0]["subtype"] == "signal_add"
    assert "101" in issues[0]["description"]


def test_signal_placement_analyzer_detects_remove():
    telemetry = {
        "nodes": [
            {
                "node_id": "202",
                "street_count": 2,
                "conflict_rate": 0.05,
                "avg_wait_time": 4.0,
                "highway": "traffic_signals",
                "lat": 14.465,
                "lon": 75.922,
            }
        ]
    }
    issues = detect_signal_placement_issues(telemetry)
    assert len(issues) == 1
    assert issues[0]["subtype"] == "signal_remove"
    assert "202" in issues[0]["description"]


def test_signal_placement_proposer():
    issues = [
        {
            "type": "signal_placement",
            "subtype": "signal_add",
            "location": {"node_id": "101", "lat": 14.464, "lon": 75.921},
            "metrics": {"street_count": 4, "conflict_rate": 0.35},
        },
        {
            "type": "signal_placement",
            "subtype": "signal_remove",
            "location": {"node_id": "202", "lat": 14.465, "lon": 75.922},
            "metrics": {"avg_wait_time": 4.0, "conflict_rate": 0.05},
        },
        {
            "type": "signal_placement",
            "subtype": "signal_relocate",
            "location": {"node_id": "303", "lat": 14.466, "lon": 75.923},
            "metrics": {"target_lat": 14.4663, "target_lon": 75.9233, "reason": "Geometric offset alignment"},
        },
    ]
    proposals = generate_signal_placement_proposals(issues, telemetry={})
    assert len(proposals) == 3
    types = [p["type"] for p in proposals]
    assert "signal_add" in types
    assert "signal_remove" in types
    assert "signal_relocate" in types


def test_intersection_simulator_analytic():
    vehicle_mix = {"cars": 60, "bikes": 30, "autos": 15, "trucks": 5, "buses": 2}
    result = simulate_intersection(
        node_id="test_node",
        vehicle_mix=vehicle_mix,
        green_s=35,
        amber_s=3,
        red_s=35,
        duration_s=300,
    )
    assert "metrics" in result
    assert "avg_wait_time_s" in result["metrics"]
    assert "throughput_veh" in result["metrics"]
    assert result["total_vehicles"] == 112
    assert result["metrics"]["avg_wait_time_s"] > 0
    assert "failing_point" in result
    assert result["failing_point"]["failing_point_veh_h"] > 0


def test_unsignalized_intersection_simulation():
    vehicle_mix = {"cars": 80, "bikes": 40, "autos": 20, "trucks": 10, "buses": 5}
    result = simulate_intersection(
        node_id="unsignal_node",
        vehicle_mix=vehicle_mix,
        is_signal=False,
        street_count=4,
        duration_s=300,
    )
    assert result["is_signal"] is False
    assert result["engine"] == "analytic_unsignalized_gap_acceptance"
    assert "collision_risk_score" in result["metrics"]
    assert 0.0 <= result["metrics"]["collision_risk_score"] <= 1.0
    assert "failing_point" in result
    assert result["failing_point"]["is_signal"] is False


def test_capacity_breakdown_analyzer():
    from simulation.capacity_breakdown_analyzer import find_failing_point

    # Test signal breakdown
    fp_sig = find_failing_point(node_id="sig_1", is_signal=True, street_count=4, green_s=30, red_s=40)
    assert fp_sig["is_signal"] is True
    assert fp_sig["failing_point_veh_h"] >= 500
    assert "breakdown_curve" in fp_sig
    assert len(fp_sig["breakdown_curve"]) > 5
    assert "failure_mode" in fp_sig
    assert "recommendation" in fp_sig

    # Test unsignalized breakdown
    fp_unsig = find_failing_point(node_id="unsig_1", is_signal=False, street_count=4)
    assert fp_unsig["is_signal"] is False
    assert fp_unsig["failing_point_veh_h"] > 0
    assert "breakdown_curve" in fp_unsig
