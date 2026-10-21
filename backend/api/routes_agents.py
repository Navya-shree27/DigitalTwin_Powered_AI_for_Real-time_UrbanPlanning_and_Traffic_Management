"""
backend/api/routes_agents.py
─────────────────────────────
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
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.db_connector import get_db
from backend.models.schema import (
    Issue, Proposal, Scenario, SimulationRun, ValidationResult,
)

log = logging.getLogger("routes_agents")
router = APIRouter(tags=["Agents & Issues"])

# Concurrency guards: track in-flight validation requests and per-proposal locks
_active_validations: set[int] = set()
_active_validations_lock = threading.Lock()
_proposal_task_locks: dict[int, threading.Lock] = {}
_task_locks_guard = threading.Lock()


def _get_proposal_task_lock(proposal_id: int) -> threading.Lock:
    with _task_locks_guard:
        if proposal_id not in _proposal_task_locks:
            _proposal_task_locks[proposal_id] = threading.Lock()
        return _proposal_task_locks[proposal_id]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _latest_done_run(scenario_id: int, db: Session) -> SimulationRun | None:
    return (
        db.query(SimulationRun)
        .filter(SimulationRun.scenario_id == scenario_id, SimulationRun.status == "done")
        .order_by(SimulationRun.finished_at.desc())
        .first()
    )


def _validate_proposal_task(
    proposal_db_id: int,
    db: Session | None = None,
    raise_on_error: bool = False,
    revalidate: bool = False,
) -> ValidationResult | None:
    """
    Background/worker task: re-simulate with proposal applied, compute comparison,
    and safely insert or update the ValidationResult (1-to-1 relationship).
    Guarded by per-proposal lock to prevent simultaneous validation runs.
    """
    task_lock = _get_proposal_task_lock(proposal_db_id)
    with task_lock:
        from backend.database.db_connector import SessionLocal
        owns_session = False
        if db is None:
            db = SessionLocal()
            owns_session = True

        try:
            proposal = db.query(Proposal).get(proposal_db_id)
            if not proposal:
                log.warning(f"Proposal {proposal_db_id} not found — cannot validate.")
                return None

            # If not revalidating, check if another concurrent task just finished validating it
            if not revalidate and proposal.validated:
                vr = db.query(ValidationResult).filter(
                    ValidationResult.proposal_id_fk == proposal_db_id
                ).first()
                if vr:
                    log.info(f"Proposal {proposal_db_id} already validated — returning existing result.")
                    return vr

            baseline_run = db.query(SimulationRun).get(proposal.run_id)
            if not baseline_run:
                log.warning(f"Baseline run for proposal {proposal_db_id} not found — cannot validate.")
                return None

            baseline_telemetry = baseline_run.get_telemetry()
            if not baseline_telemetry:
                log.warning(f"No telemetry for run {baseline_run.id} — cannot validate.")
                return None

            # Prepare normalized proposal payload for re-simulation
            params = proposal.get_parameters()
            imp = proposal.get_improvement()
            proposal_dict = {
                "proposal_id": proposal.proposal_id,
                "type": proposal.type,
                "subtype": proposal.subtype,
                "description": proposal.description,
                "parameters": params,
                "expected_improvement": imp,
            }

            # Extract target_node / target_edge if not already explicitly in params
            if "target_node" in params:
                proposal_dict["target_node"] = params["target_node"]
            elif "node_id" in params:
                proposal_dict["target_node"] = params["node_id"]
            elif proposal.type == "signal_timing" and proposal.proposal_id.startswith("signal_"):
                parts = proposal.proposal_id.split("_")
                if len(parts) >= 2 and parts[1].isdigit():
                    proposal_dict["target_node"] = int(parts[1])

            if "target_edge" in params:
                proposal_dict["target_edge"] = params["target_edge"]
            elif "edge_id" in params:
                proposal_dict["target_edge"] = params["edge_id"]
            elif "edge" in params:
                proposal_dict["target_edge"] = params["edge"]
            elif "congested_edge" in params:
                proposal_dict["target_edge"] = params["congested_edge"]

            # If issue is linked, use issue location as fallback
            if proposal.issue:
                loc = proposal.issue.get_location()
                if "target_node" not in proposal_dict and loc.get("node_id") is not None:
                    proposal_dict["target_node"] = loc.get("node_id")
                if "target_edge" not in proposal_dict and loc.get("edge_id") is not None:
                    proposal_dict["target_edge"] = loc.get("edge_id")

            # Re-simulate with proposal applied using baseline demand multiplier
            from simulation.simulation_runner import run_simulation
            demand_mult = baseline_telemetry.get("demand_multiplier")
            proposal_telemetry = run_simulation(
                scenario_id       = baseline_run.scenario_id,
                engine            = baseline_run.engine,
                duration_s        = baseline_run.duration_s,
                seed              = baseline_run.seed,
                apply_proposals   = [proposal_dict],
                demand_multiplier = demand_mult,
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

            # Upsert validation result (maintaining strict 1-to-1 data model)
            vr = db.query(ValidationResult).filter(
                ValidationResult.proposal_id_fk == proposal_db_id
            ).first()

            now = datetime.now(timezone.utc)
            if vr:
                vr.scenario_id       = baseline_run.scenario_id
                vr.verdict           = comparison["verdict"]
                vr.improvement_score = comparison["improvement_score"]
                vr.summary           = comparison["summary"]
                vr.metrics_json      = json.dumps(comparison["metrics"])
                vr.compared_at       = now
            else:
                vr = ValidationResult(
                    proposal_id_fk    = proposal_db_id,
                    scenario_id       = baseline_run.scenario_id,
                    verdict           = comparison["verdict"],
                    improvement_score = comparison["improvement_score"],
                    summary           = comparison["summary"],
                    metrics_json      = json.dumps(comparison["metrics"]),
                    compared_at       = now,
                )
                db.add(vr)

            proposal.validated = True
            db.add(proposal)

            try:
                db.commit()
            except Exception as commit_err:
                db.rollback()
                # Defensive check in case of concurrent commit
                vr_existing = db.query(ValidationResult).filter(
                    ValidationResult.proposal_id_fk == proposal_db_id
                ).first()
                if vr_existing:
                    vr_existing.scenario_id       = baseline_run.scenario_id
                    vr_existing.verdict           = comparison["verdict"]
                    vr_existing.improvement_score = comparison["improvement_score"]
                    vr_existing.summary           = comparison["summary"]
                    vr_existing.metrics_json      = json.dumps(comparison["metrics"])
                    vr_existing.compared_at       = now
                    proposal.validated = True
                    db.add(proposal)
                    db.commit()
                    vr = vr_existing
                else:
                    raise commit_err

            log.info(f"Validation complete for proposal {proposal_db_id}: {comparison['verdict']}")
            return vr

        except Exception as e:
            db.rollback()
            log.error(f"Validation failed for proposal {proposal_db_id}: {e}", exc_info=True)
            if raise_on_error:
                raise
            return None
        finally:
            with _active_validations_lock:
                _active_validations.discard(proposal_db_id)
            if owns_session:
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
        Issue.severity.asc()  # severe < moderate < low alphabetically — fine for demo
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
    revalidate: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    proposal = db.query(Proposal).get(proposal_db_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_db_id} not found.")

    if proposal.validated and not revalidate:
        vr = db.query(ValidationResult).filter(
            ValidationResult.proposal_id_fk == proposal_db_id
        ).first()
        if vr:
            return {
                "message": "Already validated.",
                "validation": vr.to_dict(),
            }

    with _active_validations_lock:
        if proposal_db_id in _active_validations:
            return {
                "message": "Validation already in progress.",
                "proposal_id": proposal_db_id,
            }
        _active_validations.add(proposal_db_id)

    background_tasks.add_task(
        _validate_proposal_task,
        proposal_db_id=proposal_db_id,
        revalidate=revalidate,
    )
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
