"""
tests/test_multi_agents.py
──────────────────────────
Unit tests for the multi-agent AI framework:
  - Base Ollama client and deterministic fallback
  - Traffic Analysis Agent
  - Safety Assessment Agent
  - Urban Planning & Optimization Agent
  - Multi-Agent Orchestrator
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from agents.multi_agent_framework import BaseAgent, OllamaClient
from agents.orchestrator import MultiAgentOrchestrator
from agents.planner_agent import UrbanPlanningAgent
from agents.safety_agent import SafetyAssessmentAgent
from agents.traffic_analysis_agent import TrafficAnalysisAgent


def _make_mock_telemetry_with_ml():
    """Create sample telemetry with ML predictions for agent testing."""
    edges = [
        {
            "edge_id": "101_102_0",
            "u": 101, "v": 102,
            "road_type": "primary",
            "lanes": 2,
            "speed_kph": 50,
            "capacity": 1800,
            "flow": 1650,
            "speed_sim": 18.5,
            "density": 89.2,
            "queue_length": 12.0,
            "wait_time": 45.0,
            "travel_time": 65.0,
            "occupancy": 0.916,
            "speed_ratio": 0.37,
            "widenable": True,
            "ml_congestion_level": 2,
            "ml_congestion_label": "Severe",
            "ml_congestion_probs": {"Low": 0.01, "Moderate": 0.09, "Severe": 0.90},
            "ml_risk_score": 0.936,
        },
        {
            "edge_id": "102_103_0",
            "u": 102, "v": 103,
            "road_type": "residential",
            "lanes": 1,
            "speed_kph": 30,
            "capacity": 400,
            "flow": 380,
            "speed_sim": 10.0,
            "density": 38.0,
            "queue_length": 6.5,
            "wait_time": 25.0,
            "travel_time": 40.0,
            "occupancy": 0.95,
            "speed_ratio": 0.33,
            "widenable": False,
            "ml_congestion_level": 2,
            "ml_congestion_label": "Severe",
            "ml_congestion_probs": {"Low": 0.02, "Moderate": 0.15, "Severe": 0.83},
            "ml_risk_score": 0.89,
        },
        {
            "edge_id": "103_104_0",
            "u": 103, "v": 104,
            "road_type": "motorway",
            "lanes": 3,
            "speed_kph": 60,
            "capacity": 2700,
            "flow": 600,
            "speed_sim": 58.0,
            "density": 10.3,
            "queue_length": 0.0,
            "wait_time": 0.0,
            "travel_time": 20.0,
            "occupancy": 0.22,
            "speed_ratio": 0.96,
            "widenable": True,
            "ml_congestion_level": 0,
            "ml_congestion_label": "Low",
            "ml_congestion_probs": {"Low": 0.95, "Moderate": 0.05, "Severe": 0.0},
            "ml_risk_score": 0.02,
        },
    ]

    nodes = [
        {"node_id": 101, "lat": 14.46, "lon": 75.92, "street_count": 4, "conflict_rate": 2.4, "avg_wait_time": 48.0},
        {"node_id": 102, "lat": 14.47, "lon": 75.93, "street_count": 3, "conflict_rate": 1.2, "avg_wait_time": 28.0},
        {"node_id": 103, "lat": 14.48, "lon": 75.94, "street_count": 2, "conflict_rate": 0.1, "avg_wait_time": 5.0},
    ]

    summary = {
        "avg_travel_time_s": 41.6,
        "avg_wait_time_s": 23.3,
        "avg_speed_kph": 28.8,
        "total_flow_veh_h": 2630,
        "congested_edges": 2,
        "congestion_ratio": 0.667,
    }

    return {"edges": edges, "nodes": nodes, "summary": summary}


class TestMultiAgentFramework:
    def test_ollama_client_config(self):
        client = OllamaClient()
        assert client.host in ("http://127.0.0.1:11434", "http://localhost:11434")
        assert client.model == "llama3.2:3b"

        custom_client = OllamaClient(host="http://127.0.0.1:11434", model="llama3.2:3b")
        assert custom_client.host == "http://127.0.0.1:11434"
        assert custom_client.model == "llama3.2:3b"

    def test_traffic_analysis_agent(self):
        agent = TrafficAnalysisAgent()
        tel = _make_mock_telemetry_with_ml()
        result = agent.run({"telemetry": tel, "scenario_name": "Test Scenario"})

        assert isinstance(result, dict)
        assert "health_status" in result
        assert "executive_summary" in result
        assert "top_bottlenecks" in result
        assert len(result["top_bottlenecks"]) > 0

    def test_safety_assessment_agent(self):
        agent = SafetyAssessmentAgent()
        tel = _make_mock_telemetry_with_ml()
        result = agent.run({"telemetry": tel})

        assert isinstance(result, dict)
        assert "safety_status" in result
        assert "safety_summary" in result
        assert "critical_intersections" in result

    def test_planner_agent(self):
        agent = UrbanPlanningAgent()
        tel = _make_mock_telemetry_with_ml()
        from agents.issue_detection.congestion_detector import detect_congestion
        issues = detect_congestion(tel)

        result = agent.run({"telemetry": tel, "issues": issues})
        assert isinstance(result, dict)
        assert "proposals" in result
        assert "planning_strategy" in result
        assert len(result["proposals"]) > 0

    def test_multi_agent_orchestrator(self):
        orchestrator = MultiAgentOrchestrator()
        tel = _make_mock_telemetry_with_ml()
        from agents.issue_detection.congestion_detector import detect_congestion
        issues = detect_congestion(tel)

        pipeline_result = orchestrator.run_pipeline(
            scenario_id=999,
            scenario_name="Test Collaborative Pipeline",
            telemetry=tel,
            issues=issues,
        )

        assert "narrative" in pipeline_result
        assert "traffic_analysis" in pipeline_result
        assert "safety_analysis" in pipeline_result
        assert "planning_strategy" in pipeline_result
        assert "proposals" in pipeline_result
        assert "top_issues" in pipeline_result
        assert len(pipeline_result["narrative"]) > 50
