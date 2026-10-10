"""
validation/report_generator.py
────────────────────────────────
Assembles a structured validation report per proposal.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("report_generator")

REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "processed" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_report(
    scenario_id: int,
    scenario_name: str,
    proposal: dict,
    comparison: dict,
    baseline_telemetry: dict,
    proposal_telemetry: dict,
) -> dict:
    """
    Generate a structured validation report and save it to disk.

    Returns the report dict.
    """
    report_id = f"report_{proposal['proposal_id']}_{scenario_id}"

    report = {
        "report_id":      report_id,
        "scenario_id":    scenario_id,
        "scenario_name":  scenario_name,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "proposal": {
            "proposal_id":  proposal.get("proposal_id"),
            "type":         proposal.get("type"),
            "description":  proposal.get("description"),
            "parameters":   proposal.get("parameters", {}),
        },
        "verdict":           comparison.get("verdict"),
        "improvement_score": comparison.get("improvement_score"),
        "summary":           comparison.get("summary"),
        "metrics":           comparison.get("metrics", {}),
        "baseline_summary":  baseline_telemetry.get("summary", {}),
        "proposal_summary":  proposal_telemetry.get("summary", {}),
    }

    # Save to disk
    out_path = REPORTS_DIR / f"{report_id}.json"
    out_path.write_text(json.dumps(report, indent=2))
    log.info(f"Report saved: {out_path}")

    return report
