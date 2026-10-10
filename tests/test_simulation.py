"""
tests/test_simulation.py
──────────────────────────
Tests for the simulation module.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
import networkx as nx

# ── SyntheticSimulator ────────────────────────────────────────────────────────

def _make_test_graph() -> nx.MultiDiGraph:
    """Create a minimal graph for testing (doesn't require OSM download)."""
    G = nx.MultiDiGraph()
    nodes = [(1, {"x": 75.92, "y": 14.46}),
             (2, {"x": 75.93, "y": 14.46}),
             (3, {"x": 75.92, "y": 14.47}),
             (4, {"x": 75.93, "y": 14.47})]
    for nid, data in nodes:
        G.add_node(nid, **data)
    edges = [
        (1, 2, {"length": 500, "speed_kph": 40, "capacity": 1200, "lanes": 2, "road_type": "primary",   "travel_time": 45}),
        (2, 3, {"length": 600, "speed_kph": 30, "capacity": 800,  "lanes": 1, "road_type": "secondary", "travel_time": 72}),
        (3, 4, {"length": 300, "speed_kph": 50, "capacity": 1800, "lanes": 3, "road_type": "motorway",  "travel_time": 21.6}),
        (4, 1, {"length": 450, "speed_kph": 40, "capacity": 1000, "lanes": 2, "road_type": "trunk",     "travel_time": 40.5}),
        (2, 4, {"length": 700, "speed_kph": 60, "capacity": 2000, "lanes": 4, "road_type": "motorway",  "travel_time": 42}),
    ]
    for u, v, data in edges:
        G.add_edge(u, v, **data)
    return G


class TestSyntheticSimulator:
    def test_run_returns_expected_keys(self):
        from simulation.simulation_runner import SyntheticSimulator
        G = _make_test_graph()
        sim = SyntheticSimulator(G, duration_s=3600, seed=42)
        result = sim.run()

        assert "engine" in result
        assert result["engine"] == "synthetic"
        assert "edges" in result
        assert "nodes" in result
        assert "summary" in result

    def test_edges_have_required_fields(self):
        from simulation.simulation_runner import SyntheticSimulator
        G = _make_test_graph()
        result = SyntheticSimulator(G, duration_s=3600, seed=42).run()
        required = {"edge_id", "flow", "speed_sim", "occupancy", "wait_time", "travel_time"}
        for edge in result["edges"]:
            assert required.issubset(set(edge.keys())), f"Edge missing fields: {edge}"

    def test_occupancy_bounded(self):
        from simulation.simulation_runner import SyntheticSimulator
        G = _make_test_graph()
        result = SyntheticSimulator(G, duration_s=3600, seed=99).run()
        for edge in result["edges"]:
            assert 0 <= edge["occupancy"] <= 1.2, f"Occupancy out of bounds: {edge['occupancy']}"

    def test_summary_metrics_positive(self):
        from simulation.simulation_runner import SyntheticSimulator
        G = _make_test_graph()
        result = SyntheticSimulator(G, duration_s=3600, seed=42).run()
        s = result["summary"]
        assert s["avg_speed_kph"] > 0
        assert s["avg_travel_time_s"] > 0
        assert 0 <= s["congestion_ratio"] <= 1

    def test_reproducible_with_same_seed(self):
        from simulation.simulation_runner import SyntheticSimulator
        G = _make_test_graph()
        r1 = SyntheticSimulator(G, duration_s=3600, seed=7).run()
        r2 = SyntheticSimulator(G, duration_s=3600, seed=7).run()
        assert r1["summary"]["avg_speed_kph"] == r2["summary"]["avg_speed_kph"]


# ── Metrics calculator ────────────────────────────────────────────────────────

class TestMetricsCalculator:
    def _sample_telemetry(self):
        from simulation.simulation_runner import SyntheticSimulator
        G = _make_test_graph()
        return SyntheticSimulator(G, duration_s=3600, seed=42).run()

    def test_compute_metrics_returns_expected_keys(self):
        from validation.metrics_calculator import compute_metrics
        tel = self._sample_telemetry()
        metrics = compute_metrics(tel)
        required = {
            "avg_travel_time_s", "avg_wait_time_s", "avg_speed_kph",
            "congestion_ratio", "efficiency_score", "emissions_proxy",
        }
        assert required.issubset(set(metrics.keys()))

    def test_efficiency_score_bounded(self):
        from validation.metrics_calculator import compute_metrics
        tel = self._sample_telemetry()
        metrics = compute_metrics(tel)
        assert 0 <= metrics["efficiency_score"] <= 100

    def test_empty_telemetry_returns_zeros(self):
        from validation.metrics_calculator import compute_metrics
        metrics = compute_metrics({"edges": [], "nodes": []})
        assert metrics["avg_speed_kph"] == 0
        assert metrics["efficiency_score"] == 0
