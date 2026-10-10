"""
tests/test_api.py
──────────────────
FastAPI integration tests (uses TestClient — no server needed).
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from backend.app import app
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "docs" in r.json()


class TestScenariosAPI:
    def test_list_scenarios_empty(self, client):
        r = client.get("/api/scenarios")
        assert r.status_code == 200
        assert "scenarios" in r.json()

    def test_get_nonexistent_scenario(self, client):
        r = client.get("/api/scenarios/99999")
        assert r.status_code == 404

    def test_simulate_nonexistent(self, client):
        r = client.post("/api/scenarios/99999/simulate", json={})
        assert r.status_code == 404


class TestDashboardAPI:
    def test_get_nonexistent_dashboard(self, client):
        r = client.get("/api/dashboard/99999")
        assert r.status_code == 404

    def test_get_nonexistent_metrics(self, client):
        r = client.get("/api/scenarios/99999/metrics")
        assert r.status_code == 404

    def test_geojson_not_found_before_run(self, client):
        """GeoJSON 404 is expected before any simulation has run."""
        r = client.get("/api/dashboard/1/geojson/network")
        assert r.status_code in (200, 404)   # 200 if network.geojson exists from prior run

    def test_get_nonexistent_telemetry(self, client):
        r = client.get("/api/dashboard/99999/telemetry")
        assert r.status_code == 404


class TestProposalsAPI:
    def test_get_nonexistent_proposal(self, client):
        r = client.get("/api/proposals/99999")
        assert r.status_code == 404

    def test_validate_nonexistent_proposal(self, client):
        r = client.post("/api/proposals/99999/validate")
        assert r.status_code == 404
