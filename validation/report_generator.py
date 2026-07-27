"""
validation/report_generator.py
────────────────────────────────
Assembles a structured validation report per proposal and writes engineering markdown reports to the reports/ directory.
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
    Generate a structured validation report, save it to disk, and export markdown reports.

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

    # Save JSON to disk
    out_path = REPORTS_DIR / f"{report_id}.json"
    out_path.write_text(json.dumps(report, indent=2))
    log.info(f"JSON Report saved: {out_path}")

    # Export markdown reports to root reports/ directory (Aimsun/Vissim inspired)
    try:
        reports_root = Path(__file__).resolve().parent.parent / "reports"
        reports_root.mkdir(parents=True, exist_ok=True)

        # 1. current_network_report.md
        net_report = f"""# Current Road Network Report

Scenario: **{scenario_name}** (ID: {scenario_id})
Generated at: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")} UTC

## Network Summary
- **Total Edges**: {report['baseline_summary'].get('total_edges', 'N/A')}
- **Congested Edges**: {report['baseline_summary'].get('congested_edges', 'N/A')}
- **Congestion Ratio**: {report['baseline_summary'].get('congestion_ratio', 0.0) * 100:.1f}%

## Baseline Performance KPIs
- **Average Speed**: {report['baseline_summary'].get('avg_speed_kph', 'N/A')} km/h
- **Average Travel Time**: {report['baseline_summary'].get('avg_travel_time_s', 'N/A')} s
- **Average Wait Time (Stopped Delay)**: {report['baseline_summary'].get('avg_wait_time_s', 'N/A')} s
- **Level of Service (LOS)**: **LOS {report['baseline_summary'].get('level_of_service', 'A')}**
- **Composite Efficiency Score**: {report['baseline_summary'].get('efficiency_score', 'N/A')}/100
"""
        (reports_root / "current_network_report.md").write_text(net_report, encoding="utf-8")

        # 2. congestion_report.md
        edges = baseline_telemetry.get("edges", [])
        congested_edges = [e for e in edges if e.get("occupancy", 0.0) > 0.50]
        congested_edges_sorted = sorted(congested_edges, key=lambda e: e.get("occupancy", 0.0), reverse=True)

        table_rows = []
        for e in congested_edges_sorted[:10]:
            table_rows.append(f"| {e['edge_id']} | {e.get('road_type', 'road')} | {e.get('occupancy', 0.0)*100:.1f}% | {e.get('speed_sim', 0.0):.1f} | {e.get('queue_length', 0.0):.1f} |")
        table_content = "\n".join(table_rows) if table_rows else "| - | - | - | - | - |"

        congestion_report = f"""# Network Congestion Analysis Report

Scenario: **{scenario_name}**
This report highlights the main road bottlenecks and congested corridors identified during the baseline simulation run.

## Top Congested Road Segments
| Edge ID | Road Type | Occupancy | Avg Speed (km/h) | Avg Queue (Vehicles) |
|---|---|---|---|---|
{table_content}

## Observations
- The network exhibits an overall congestion ratio of **{report['baseline_summary'].get('congestion_ratio', 0.0)*100:.1f}%**.
- Saturated corridors lead to increased queuing delays and elevated tailpipe emissions.
"""
        (reports_root / "congestion_report.md").write_text(congestion_report, encoding="utf-8")

        # 3. signal_analysis.md
        nodes = baseline_telemetry.get("nodes", [])
        junctions_sorted = sorted([n for n in nodes if n.get("street_count", 0) >= 3], key=lambda n: n.get("avg_wait_time", 0.0), reverse=True)

        node_rows = []
        for n in junctions_sorted[:10]:
            node_rows.append(f"| {n['node_id']} | {n.get('street_count', 3)}-way | {n.get('avg_wait_time', 0.0):.1f}s | {n.get('conflict_rate', 0.0):.2f} conflict/h |")
        node_content = "\n".join(node_rows) if node_rows else "| - | - | - | - |"

        signal_report = f"""# Intersection Signal Timing & Safety Analysis

Scenario: **{scenario_name}**
This report evaluates active signal timings and conflict rates across major network junctions.

## Junction Performance Indices
| Node ID | Approaches | Average Stopped Delay | Conflict Rate |
|---|---|---|---|
{node_content}

## Rationale
- Junctions with delays exceeding 55s operate at **LOS E/F** and represent primary targets for signal retiming using Webster's equation.
"""
        (reports_root / "signal_analysis.md").write_text(signal_report, encoding="utf-8")

        # 4. recommended_changes.md
        recommended_changes = f"""# Proposed AI Infrastructure & Signal Recommender

Scenario: **{scenario_name}**
This report documents the specific optimization parameters proposed to resolve identified planning flaws.

## Active Proposal Profile
- **Proposal ID**: `{proposal.get("proposal_id")}`
- **Type**: **{proposal.get("type", "Custom Edit").upper()}**
- **Description**: {proposal.get("description", "No description provided.")}

## Revision Parameters
```json
{json.dumps(proposal.get("parameters", {}), indent=2)}
```

## Rationale & Objectives
- **Target Location**: {proposal.get("location", {}).get("edge_id") or proposal.get("location", {}).get("node_id") or "Network-wide"}
- **Expected Outcome**: {comparison.get("summary", "Optimization of flow performance and reduction of queue buildup.")}
"""
        (reports_root / "recommended_changes.md").write_text(recommended_changes, encoding="utf-8")

        # 5. best_scenario.md
        metrics = comparison.get("metrics", {})
        metrics_rows = []
        for kpi, diff in metrics.items():
            improved_symbol = "✅" if diff.get("improved") else "❌"
            metrics_rows.append(f"| {kpi.replace('_', ' ').title()} | {diff.get('before')} | {diff.get('after')} | {diff.get('delta_pct'):+.1f}% | {improved_symbol} |")
        metrics_content = "\n".join(metrics_rows)

        best_scenario = f"""# Scenario Comparative Validation Report

This report evaluates and ranks the performance improvements of the proposed scenario configurations against the baseline model.

## Verdict: **{comparison.get("verdict")}** (Score: {comparison.get("improvement_score")}/100)

## KPI Before vs. After Comparison
| Metric (KPI) | Baseline (Before) | Optimized (After) | Delta % | Improved |
|---|---|---|---|---|
{metrics_content}

## Summary Recommendation
{comparison.get("summary")}

*Inspired by Aimsun Level of Service audits and PTV Vissim micro-simulation engineering reports.*
"""
        (reports_root / "best_scenario.md").write_text(best_scenario, encoding="utf-8")
        log.info("Markdown Reports successfully exported to reports/ folder.")

    except Exception as e:
        log.error(f"Failed to export markdown reports to root directory: {e}", exc_info=True)

    return report
