"""
backend/api/routes_ai.py
─────────────────────────
Endpoints for issues, proposals, and proposal validation.

Endpoints
─────────
  GET  /api/scenarios/{scenario_id}/issues     — list all issues for the latest run
  GET  /api/scenarios/{scenario_id}/proposals  — list all proposals for the latest run
  POST /api/proposals/{proposal_db_id}/validate — validate (re-simulate) a proposal
  GET  /api/proposals/{proposal_db_id}          — get proposal detail + validation result
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db_connector import get_db
from backend.models.schema import (
    Issue, Proposal, Scenario, SimulationRun, ValidationResult,
)

log = logging.getLogger("routes_ai")
router = APIRouter(tags=["AI & Issues"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_done_run(scenario_id: int, db: Session) -> SimulationRun | None:
    return (
        db.query(SimulationRun)
        .filter(SimulationRun.scenario_id == scenario_id, SimulationRun.status == "done")
        .order_by(SimulationRun.finished_at.desc())
        .first()
    )


# Track in-progress validations so frontend can poll status
_validation_status: dict[int, str] = {}  # proposal_db_id -> "pending" | "done" | "failed"


def _validate_proposal_task(proposal_db_id: int):
    """Background task: re-simulate with proposal applied, compute comparison."""
    from backend.database.db_connector import SessionLocal
    _validation_status[proposal_db_id] = "pending"
    db = SessionLocal()
    try:
        proposal = db.query(Proposal).get(proposal_db_id)
        if not proposal:
            _validation_status[proposal_db_id] = "failed"
            return

        baseline_run = db.query(SimulationRun).get(proposal.run_id)
        if not baseline_run:
            _validation_status[proposal_db_id] = "failed"
            return

        baseline_telemetry = baseline_run.get_telemetry()
        if not baseline_telemetry:
            log.warning(f"No telemetry for run {baseline_run.id} — cannot validate.")
            _validation_status[proposal_db_id] = "failed"
            return

        # Re-simulate with proposal applied.
        # ALWAYS use synthetic engine for validation — SUMO may not be available
        # and validation only needs relative delta, not absolute SUMO accuracy.
        from simulation.simulation_runner import run_simulation
        params = proposal.get_parameters()
        proposal_telemetry = run_simulation(
            scenario_id     = baseline_run.scenario_id,
            engine          = "synthetic",          # always synthetic for validation
            duration_s      = baseline_run.duration_s or 3600,
            seed            = (baseline_run.seed or 42) + 1,  # different seed → distinct sample
            apply_proposals = [params],
        )

        # Compute metrics for both
        from validation.metrics_calculator import compute_metrics
        baseline_metrics = compute_metrics(baseline_telemetry)
        proposal_metrics = compute_metrics(proposal_telemetry)

        # Compare
        from validation.before_after_comparator import compare
        comparison = compare(
            baseline_metrics = baseline_metrics,
            proposal_metrics = proposal_metrics,
            proposal_id      = proposal.proposal_id,
            scenario_id      = baseline_run.scenario_id,
        )

        # Remove stale validation result if it exists (re-validate scenario)
        existing_vr = db.query(ValidationResult).filter(
            ValidationResult.proposal_id_fk == proposal_db_id
        ).first()
        if existing_vr:
            db.delete(existing_vr)
            db.flush()

        # Save new validation result
        vr = ValidationResult(
            proposal_id_fk    = proposal_db_id,
            scenario_id       = baseline_run.scenario_id,
            verdict           = comparison["verdict"],
            improvement_score = comparison["improvement_score"],
            summary           = comparison["summary"],
            metrics_json      = json.dumps(comparison["metrics"]),
        )
        db.add(vr)

        proposal.validated = True
        db.add(proposal)
        db.commit()
        _validation_status[proposal_db_id] = "done"
        log.info(f"Validation complete for proposal {proposal_db_id}: {comparison['verdict']}")

        # Generate markdown reports (non-critical)
        try:
            from validation.report_generator import generate_report
            from backend.models.schema import Scenario
            scenario = db.query(Scenario).get(baseline_run.scenario_id)
            scenario_name = scenario.name if scenario else "Unknown Scenario"
            generate_report(
                scenario_id=baseline_run.scenario_id,
                scenario_name=scenario_name,
                proposal=proposal.to_dict(),
                comparison=comparison,
                baseline_telemetry=baseline_telemetry,
                proposal_telemetry=proposal_telemetry
            )
        except Exception as rep_err:
            log.warning(f"Report generation failed (non-critical): {rep_err}")

    except Exception as e:
        log.error(f"Validation failed for proposal {proposal_db_id}: {e}", exc_info=True)
        _validation_status[proposal_db_id] = "failed"
    finally:
        db.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/scenarios/{scenario_id}/issues")
def get_issues(
    scenario_id: int,
    severity: str | None = None,
    issue_type: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> dict:
    run = _latest_done_run(scenario_id, db)
    if not run:
        raise HTTPException(404, f"No completed simulation run found for scenario {scenario_id}.")

    query = db.query(Issue).filter(Issue.run_id == run.id)
    if severity:
        query = query.filter(Issue.severity == severity)
    if issue_type:
        query = query.filter(Issue.type == issue_type)

    issues = query.order_by(
        Issue.severity.asc()
    ).limit(limit).all()

    # Better sort: severe first
    priority = {"severe": 0, "moderate": 1, "low": 2}
    issues_sorted = sorted(issues, key=lambda i: priority.get(i.severity, 3))

    return {
        "scenario_id": scenario_id,
        "run_id":      run.id,
        "total":       len(issues_sorted),
        "issues":      [i.to_dict() for i in issues_sorted],
    }


@router.get("/api/scenarios/{scenario_id}/proposals")
def get_proposals(
    scenario_id: int,
    proposal_type: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> dict:
    run = _latest_done_run(scenario_id, db)
    if not run:
        raise HTTPException(404, f"No completed simulation run found for scenario {scenario_id}.")

    query = db.query(Proposal).filter(Proposal.run_id == run.id)
    if proposal_type:
        query = query.filter(Proposal.type == proposal_type)

    proposals = query.limit(limit).all()
    return {
        "scenario_id": scenario_id,
        "run_id":      run.id,
        "total":       len(proposals),
        "proposals":   [p.to_dict() for p in proposals],
    }


@router.post("/api/proposals/{proposal_db_id}/validate", status_code=202)
def validate_proposal(
    proposal_db_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> dict:
    proposal = db.query(Proposal).get(proposal_db_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_db_id} not found.")

    # If already validated, allow re-validation by resetting the flag
    if proposal.validated:
        vr = db.query(ValidationResult).filter(
            ValidationResult.proposal_id_fk == proposal_db_id
        ).first()
        if vr:
            return {
                "message": "Already validated.",
                "validation": vr.to_dict(),
            }
        # validated flag set but no result — reset and re-run
        proposal.validated = False
        db.add(proposal)
        db.commit()

    # Mark as pending immediately so frontend polling can detect it
    _validation_status[proposal_db_id] = "pending"
    background_tasks.add_task(_validate_proposal_task, proposal_db_id=proposal_db_id)
    return {
        "message": "Validation started in background.",
        "proposal_id": proposal_db_id,
        "status": "pending"
    }


@router.get("/api/proposals/{proposal_db_id}/validate/status")
def get_validation_status(
    proposal_db_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Poll endpoint — returns 'pending', 'done', or 'failed'."""
    # Check in-memory status first (hot path)
    status = _validation_status.get(proposal_db_id, None)

    # Check DB regardless
    proposal = db.query(Proposal).get(proposal_db_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_db_id} not found.")

    if proposal.validated:
        vr = db.query(ValidationResult).filter(
            ValidationResult.proposal_id_fk == proposal_db_id
        ).first()
        return {
            "status": "done",
            "proposal_id": proposal_db_id,
            "validation": vr.to_dict() if vr else None,
        }

    return {
        "status": status or "pending",
        "proposal_id": proposal_db_id,
        "validation": None,
    }


@router.get("/api/proposals/{proposal_db_id}")
def get_proposal(proposal_db_id: int, db: Session = Depends(get_db)) -> dict:
    proposal = db.query(Proposal).get(proposal_db_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_db_id} not found.")

    vr = db.query(ValidationResult).filter(
        ValidationResult.proposal_id_fk == proposal_db_id
    ).first()

    return {
        "proposal":   proposal.to_dict(),
        "validation": vr.to_dict() if vr else None,
    }
