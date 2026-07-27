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


def _validate_proposal_task(proposal_db_id: int):
    """Background task: re-simulate with proposal applied, compute comparison."""
    from backend.database.db_connector import SessionLocal
    db = SessionLocal()
    try:
        proposal = db.query(Proposal).get(proposal_db_id)
        if not proposal:
            return

        baseline_run = db.query(SimulationRun).get(proposal.run_id)
        if not baseline_run:
            return

        baseline_telemetry = baseline_run.get_telemetry()
        if not baseline_telemetry:
            log.warning(f"No telemetry for run {baseline_run.id} — cannot validate.")
            return

        # Re-simulate with proposal applied
        from simulation.simulation_runner import run_simulation
        params = proposal.get_parameters()
        proposal_telemetry = run_simulation(
            scenario_id     = baseline_run.scenario_id,
            engine          = baseline_run.engine,
            duration_s      = baseline_run.duration_s,
            seed            = baseline_run.seed,
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

        # Save validation result
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
        log.info(f"Validation complete for proposal {proposal_db_id}: {comparison['verdict']}")

        # Generate markdown reports as well
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
            log.error(f"Failed to generate markdown report: {rep_err}", exc_info=True)

    except Exception as e:
        log.error(f"Validation failed for proposal {proposal_db_id}: {e}", exc_info=True)
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

    if proposal.validated:
        vr = db.query(ValidationResult).filter(
            ValidationResult.proposal_id_fk == proposal_db_id
        ).first()
        return {
            "message": "Already validated.",
            "validation": vr.to_dict() if vr else None,
        }

    background_tasks.add_task(_validate_proposal_task, proposal_db_id=proposal_db_id)
    return {"message": "Validation started in background.", "proposal_id": proposal_db_id}


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
