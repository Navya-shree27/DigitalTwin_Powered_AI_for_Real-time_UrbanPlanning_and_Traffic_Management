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
    ]
    proposals = generate_signal_placement_proposals(issues, telemetry={})
    assert len(proposals) == 2
    types = [p["type"] for p in proposals]
    assert "signal_add" in types
    assert "signal_remove" in types


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
