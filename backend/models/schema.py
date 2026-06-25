"""
backend/models/schema.py
─────────────────────────
SQLAlchemy ORM models for the Digital Twin Traffic AI system.

Tables
──────
  scenarios          : A named city simulation scenario.
  simulation_runs    : A completed simulation run attached to a scenario.
  issues             : Detected traffic issues for a run.
  proposals          : AI-generated intervention proposals.
  validation_results : Before/after comparison for a validated proposal.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import relationship

from backend.database.db_connector import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────

class Scenario(Base):
    __tablename__ = "scenarios"

    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String(255), nullable=False)
    city        = Column(String(255), nullable=False, default="Davanagere, Karnataka, India")
    description = Column(Text, default="")
    created_at  = Column(DateTime, default=_now)
    updated_at  = Column(DateTime, default=_now, onupdate=_now)

    # Geospatial metadata (from osm_to_network)
    bbox_north  = Column(Float, nullable=True)
    bbox_south  = Column(Float, nullable=True)
    bbox_east   = Column(Float, nullable=True)
    bbox_west   = Column(Float, nullable=True)
    n_nodes     = Column(Integer, nullable=True)
    n_edges     = Column(Integer, nullable=True)

    runs        = relationship("SimulationRun", back_populates="scenario", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "city": self.city,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "bbox": {
                "north": self.bbox_north, "south": self.bbox_south,
                "east":  self.bbox_east,  "west":  self.bbox_west,
            },
            "n_nodes": self.n_nodes, "n_edges": self.n_edges,
        }


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id          = Column(Integer, primary_key=True, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False)
    engine      = Column(String(50), default="synthetic")
    duration_s  = Column(Integer, default=3600)
    seed        = Column(Integer, default=42)
    status      = Column(String(50), default="pending")  # pending | running | done | failed
    is_baseline = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=_now)
    finished_at = Column(DateTime, nullable=True)

    # Aggregate KPI columns (from metrics_calculator)
    avg_travel_time_s = Column(Float, nullable=True)
    avg_wait_time_s   = Column(Float, nullable=True)
    avg_speed_kph     = Column(Float, nullable=True)
    congestion_ratio  = Column(Float, nullable=True)
    total_delay_s     = Column(Float, nullable=True)
    emissions_proxy   = Column(Float, nullable=True)
    efficiency_score  = Column(Float, nullable=True)
    throughput_index  = Column(Float, nullable=True)
    noise_pollution_db = Column(Float, nullable=True)

    # Full telemetry JSON (may be large — consider offloading to a file in Phase B)
    telemetry_json = Column(Text, nullable=True)

    scenario  = relationship("Scenario", back_populates="runs")
    issues    = relationship("Issue", back_populates="run", cascade="all, delete-orphan")
    proposals = relationship("Proposal", back_populates="run", cascade="all, delete-orphan")

    def get_telemetry(self) -> dict:
        return json.loads(self.telemetry_json) if self.telemetry_json else {}

    def set_telemetry(self, t: dict) -> None:
        self.telemetry_json = json.dumps(t)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "scenario_id": self.scenario_id,
            "engine": self.engine, "duration_s": self.duration_s,
            "seed": self.seed, "status": self.status,
            "is_baseline": self.is_baseline,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "metrics": {
                "avg_travel_time_s": self.avg_travel_time_s,
                "avg_wait_time_s":   self.avg_wait_time_s,
                "avg_speed_kph":     self.avg_speed_kph,
                "congestion_ratio":  self.congestion_ratio,
                "total_delay_s":     self.total_delay_s,
                "emissions_proxy":   self.emissions_proxy,
                "efficiency_score":  self.efficiency_score,
                "throughput_index":  self.throughput_index,
                "noise_pollution_db": self.noise_pollution_db,
            },
        }


class Issue(Base):
    __tablename__ = "issues"

    id          = Column(Integer, primary_key=True, index=True)
    run_id      = Column(Integer, ForeignKey("simulation_runs.id", ondelete="CASCADE"))
    issue_id    = Column(String(255), nullable=False, index=True)
    type        = Column(String(100), nullable=False)  # congestion | intersection_safety | lane_utilization
    subtype     = Column(String(100), nullable=True)
    severity    = Column(String(50), nullable=False)   # severe | moderate | low
    description = Column(Text, default="")
    location_json = Column(Text, default="{}")        # {edge_id, node_id, lat, lon, …}
    metrics_json  = Column(Text, default="{}")
    detected_at   = Column(DateTime, default=_now)

    run      = relationship("SimulationRun", back_populates="issues")
    proposals = relationship("Proposal", back_populates="issue", cascade="all, delete-orphan")

    def get_location(self) -> dict:
        return json.loads(self.location_json) if self.location_json else {}

    def get_metrics(self) -> dict:
        return json.loads(self.metrics_json) if self.metrics_json else {}

    def to_dict(self) -> dict:
        return {
            "id": self.id, "run_id": self.run_id,
            "issue_id": self.issue_id, "type": self.type,
            "subtype": self.subtype, "severity": self.severity,
            "description": self.description,
            "location": self.get_location(),
            "metrics":  self.get_metrics(),
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
        }


class Proposal(Base):
    __tablename__ = "proposals"

    id          = Column(Integer, primary_key=True, index=True)
    run_id      = Column(Integer, ForeignKey("simulation_runs.id", ondelete="CASCADE"))
    issue_id_fk = Column(Integer, ForeignKey("issues.id", ondelete="CASCADE"), nullable=True)
    proposal_id = Column(String(255), nullable=False, index=True)
    type        = Column(String(100), nullable=False)  # signal_timing | lane_change | route_diversion
    subtype     = Column(String(100), nullable=True)
    description = Column(Text, default="")
    parameters_json    = Column(Text, default="{}")
    improvement_json   = Column(Text, default="{}")
    generated_at       = Column(DateTime, default=_now)
    validated          = Column(Boolean, default=False)

    run   = relationship("SimulationRun", back_populates="proposals")
    issue = relationship("Issue", back_populates="proposals")
    validation_result = relationship(
        "ValidationResult", back_populates="proposal", uselist=False,
        cascade="all, delete-orphan"
    )

    def get_parameters(self) -> dict:
        return json.loads(self.parameters_json) if self.parameters_json else {}

    def get_improvement(self) -> dict:
        return json.loads(self.improvement_json) if self.improvement_json else {}

    def to_dict(self) -> dict:
        return {
            "id": self.id, "run_id": self.run_id,
            "proposal_id": self.proposal_id,
            "type": self.type, "subtype": self.subtype,
            "description": self.description,
            "parameters":  self.get_parameters(),
            "expected_improvement": self.get_improvement(),
            "generated_at": self.generated_at.isoformat() if self.generated_at else None,
            "validated": self.validated,
        }


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id                = Column(Integer, primary_key=True, index=True)
    proposal_id_fk    = Column(Integer, ForeignKey("proposals.id", ondelete="CASCADE"), unique=True)
    scenario_id       = Column(Integer, nullable=False)
    verdict           = Column(String(50), nullable=False)
    improvement_score = Column(Float, default=0)
    summary           = Column(Text, default="")
    metrics_json      = Column(Text, default="{}")
    compared_at       = Column(DateTime, default=_now)

    proposal = relationship("Proposal", back_populates="validation_result")

    def get_metrics(self) -> dict:
        return json.loads(self.metrics_json) if self.metrics_json else {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "proposal_id_fk": self.proposal_id_fk,
            "scenario_id": self.scenario_id,
            "verdict": self.verdict,
            "improvement_score": self.improvement_score,
            "summary": self.summary,
            "metrics": self.get_metrics(),
            "compared_at": self.compared_at.isoformat() if self.compared_at else None,
        }
