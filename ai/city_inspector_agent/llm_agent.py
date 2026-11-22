"""
ai/city_inspector_agent/llm_agent.py
─────────────────────────────────────────
LLM-based City Inspector Agent.

Receives structured simulation summaries, calls the Ollama local LLM
(llama3.2 / digital-twin-inspector), and returns a human-readable narrative
analysis plus a structured priorities list.

Graceful degradation
────────────────────
If Ollama is not reachable, the agent falls back to a deterministic rule-based
summary so the rest of the pipeline still works.

Provider priority (auto-detected from .env):
  1. ollama  — local Ollama (default; uses OLLAMA_MODEL_INSPECTOR)
  2. anthropic — cloud Claude (requires ANTHROPIC_API_KEY)
  3. rule-based — deterministic fallback (no AI)

Usage
─────
    from ai.city_inspector_agent.llm_agent import CityInspectorAgent
    agent = CityInspectorAgent()
    result = agent.analyze(scenario_id=1, scenario_name="...", telemetry=telemetry, issues=issues)
    print(result["narrative"])
"""

from __future__ import annotations

import logging
import os
import textwrap
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("llm_agent")

PROMPTS_DIR = Path(__file__).parent / "prompts"

# ── Try importing Anthropic (optional) ───────────────────────────────────────
try:
    import anthropic  # type: ignore
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False
    log.debug("anthropic package not installed — Ollama will be used instead.")


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder helpers
# ─────────────────────────────────────────────────────────────────────────────

def _build_analysis_prompt(
    scenario_name: str,
    telemetry: dict,
    issues: list[dict],
    prior_summary: str,
) -> str:
    summary = telemetry.get("summary", {})
    edges   = telemetry.get("edges", [])
    engine  = telemetry.get("engine", "unknown")

    # Top 5 most congested edges (by occupancy)
    sorted_edges = sorted(edges, key=lambda e: e.get("occupancy", 0), reverse=True)[:5]
    congested_table = "\n".join(
        f"  • Edge {e['edge_id']} ({e.get('road_type','?')}): "
        f"occupancy={e.get('occupancy', 0):.1%}, "
        f"speed={e.get('speed_sim', 0):.1f} km/h, "
        f"queue={e.get('queue_length', 0):.1f} veh, "
        f"widenable={e.get('widenable', True)}"
        for e in sorted_edges
    ) or "  (none)"

    # Issues summary
    severe   = [i for i in issues if i["severity"] == "severe"]
    moderate = [i for i in issues if i["severity"] == "moderate"]
    low      = [i for i in issues if i["severity"] == "low"]

    issues_text = ""
    for issue in (severe + moderate)[:10]:
        issues_text += (
            f"  [{issue['severity'].upper()}] {issue['type']} — "
            f"{issue.get('description', '')[:120]}\n"
        )
    if not issues_text:
        issues_text = "  (no issues detected)"

    prompt = textwrap.dedent(f"""
    === SIMULATION TELEMETRY SUMMARY ===
    Scenario: {scenario_name}
    Simulation Engine: {engine}
    Duration: {telemetry.get('duration_s', 'N/A')}s
    Generated: {telemetry.get('generated_at', 'N/A')}

    --- NETWORK SUMMARY ---
    Total edges: {len(edges)}
    Average simulated speed: {summary.get('avg_speed_kph', 0):.1f} km/h
    Average travel time: {summary.get('avg_travel_time_s', 0):.1f}s
    Average wait time: {summary.get('avg_wait_time_s', 0):.1f}s
    Total flow: {summary.get('total_flow_veh_h', 0):.0f} vehicles/hour
    Congested edges: {summary.get('congested_edges', 0)} / {len(edges)} ({summary.get('congestion_ratio', 0):.1%})

    --- TOP CONGESTED EDGES (by occupancy) ---
    {congested_table}

    --- DETECTED ISSUES ---
    Severe:   {len(severe)}
    Moderate: {len(moderate)}
    Low:      {len(low)}

    Issue details:
    {issues_text}

    --- PRIOR CYCLE MEMORY ---
    {prior_summary}

    === YOUR TASK ===
    Based on the above simulation data:
    1. Summarize the overall traffic health of this network in 2-3 sentences.
    2. Identify the top 3 most critical issues and explain the likely root cause of each.
    3. For each critical issue, suggest 1-2 concrete interventions (keeping in mind that if 'widenable=False' on a road, physical widening is blocked by building footprints, so you must recommend timing adjustments, transit priority, or routing instead of widening).
    4. If prior cycle data is available, comment on trend (improving/worsening).
    5. Flag any unusual patterns or anomalies.

    Be concise and data-grounded. Address a city planner audience.
    """).strip()
    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback (no API key)
# ─────────────────────────────────────────────────────────────────────────────

def _rule_based_summary(telemetry: dict, issues: list[dict]) -> str:
    summary      = telemetry.get("summary", {})
    congestion_r = summary.get("congestion_ratio", 0)
    avg_speed    = summary.get("avg_speed_kph", 0)
    avg_wait     = summary.get("avg_wait_time_s", 0)
    severe_count = sum(1 for i in issues if i["severity"] == "severe")

    health = "poor" if congestion_r > 0.3 else ("moderate" if congestion_r > 0.15 else "good")

    lines = [
        f"[Rule-based summary — no LLM API key configured]",
        f"",
        f"Network health: {health.upper()}",
        f"• Average speed: {avg_speed:.1f} km/h | Average wait: {avg_wait:.1f}s",
        f"• Congestion ratio: {congestion_r:.1%} ({summary.get('congested_edges', 0)} congested edges)",
        f"• Severe issues detected: {severe_count}",
        f"",
        f"Top issues:",
    ]
    severe_issues = [i for i in issues if i["severity"] == "severe"][:3]
    for i, issue in enumerate(severe_issues, 1):
        lines.append(f"  {i}. [{issue['type']}] {issue.get('description', '')[:100]}")
    if not severe_issues:
        lines.append("  No severe issues detected.")
    lines.append("")
    lines.append("To enable AI narrative analysis, set LLM_PROVIDER=ollama in .env and ensure Ollama is running (ollama serve)")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Main agent class
# ─────────────────────────────────────────────────────────────────────────────

class CityInspectorAgent:
    """
    LLM-powered City Inspector Agent.

    Analyzes simulation telemetry and detected issues, returns a structured
    response with a human-readable narrative and prioritized recommendations.

    Provider priority (from .env):
      1. ollama    — local Ollama (OLLAMA_MODEL_INSPECTOR or OLLAMA_MODEL)
      2. anthropic — cloud Claude (ANTHROPIC_API_KEY)
      3. rule-based — deterministic fallback
    """

    ANTHROPIC_MODEL = "claude-3-5-sonnet-20241022"
    MAX_TOKENS = 1024

    SYSTEM_PROMPT = (
        "You are the AI City Inspector Agent, an expert urban traffic analyst "
        "embedded in a Digital Twin traffic management system for Davanagere, Karnataka, India. "
        "Be concise, data-grounded, and authoritative. Address a city planner audience. "
        "If widenable=False on a road, never recommend physical widening — "
        "use signal timing, transit priority, or routing instead."
    )

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "").lower()
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")

        # Ollama config — use the shared OllamaClient
        from ai.ollama_client import get_ollama_client
        self._ollama = get_ollama_client()

        # Resolve model name for the inspector role
        self._ollama_model = self._ollama.resolve_model("inspector")

        # Auto-detect provider:
        if not self.provider:
            if self._ollama.is_available():
                self.provider = "ollama"
            elif self.anthropic_key:
                self.provider = "anthropic"
            else:
                self.provider = "rule-based"

        # Initialize Anthropic client if needed
        self._anthropic_client = None
        if self.provider == "anthropic" and self.anthropic_key and _ANTHROPIC_AVAILABLE:
            self._anthropic_client = anthropic.Anthropic(api_key=self.anthropic_key)
            log.info("CityInspectorAgent initialized with Claude API.")
        elif self.provider == "ollama":
            if self._ollama.is_available():
                log.info(
                    f"CityInspectorAgent initialized with Ollama model "
                    f"'{self._ollama_model}' at {self._ollama.host}."
                )
            else:
                log.warning("Ollama not reachable — falling back to rule-based mode.")
                self.provider = "rule-based"
        else:
            log.warning(
                f"CityInspectorAgent in rule-based mode. "
                f"Provider '{self.provider}' not available or keys missing."
            )

    def _call_llm(self, prompt: str) -> str:
        """Call the selected LLM provider and return the response text."""
        if self.provider == "ollama" and self._ollama.is_available():
            return self._ollama.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=self.SYSTEM_PROMPT,
                role="inspector",
                temperature=0.3,
                max_tokens=self.MAX_TOKENS,
            )

        elif self.provider == "anthropic" and self._anthropic_client:
            message = self._anthropic_client.messages.create(
                model=self.ANTHROPIC_MODEL,
                max_tokens=self.MAX_TOKENS,
                system=self.SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text

        else:
            raise RuntimeError("No valid LLM client/provider configured.")

    def analyze(
        self,
        scenario_id: int,
        scenario_name: str,
        telemetry: dict,
        issues: list[dict],
    ) -> dict:
        """
        Run a full analysis cycle.

        Parameters
        ──────────
        scenario_id   : DB ID of the scenario.
        scenario_name : Human-readable scenario name.
        telemetry     : Full telemetry dict from simulation_runner.
        issues        : Combined list of all detected issues.

        Returns
        ───────
        {
          "narrative":       str,    # human-readable analysis
          "top_issues":      list,   # top 3–5 issues (from input list)
          "recommendations": list,   # list of recommendation strings
          "memory_summary":  str,    # short summary for memory store
          "model":           str,    # "claude-..." or "rule-based"
        }
        """
        from ai.city_inspector_agent.agent_memory import get_memory
        memory = get_memory()
        prior_summary = memory.get_prior_summary(scenario_id)

        # ── LLM or fallback ───────────────────────────────────────────────────
        if self.provider == "ollama" or (self.provider == "anthropic" and self._anthropic_client):
            prompt = _build_analysis_prompt(scenario_name, telemetry, issues, prior_summary)
            try:
                narrative = self._call_llm(prompt)
                model_used = self._ollama_model if self.provider == "ollama" else self.ANTHROPIC_MODEL
            except Exception as e:
                log.error(f"LLM call failed: {e}. Falling back to rule-based summary.")
                narrative = _rule_based_summary(telemetry, issues)
                model_used = f"rule-based (llm-error: {type(e).__name__})"
        else:
            narrative = _rule_based_summary(telemetry, issues)
            model_used = "rule-based"

        # ── Top issues ────────────────────────────────────────────────────────
        priority = {"severe": 0, "moderate": 1, "low": 2}
        top_issues = sorted(issues, key=lambda x: priority.get(x["severity"], 3))[:5]

        # ── Recommendations (parsed from narrative or rule-based) ─────────────
        recommendations = _extract_recommendations(narrative)

        # ── Update memory ─────────────────────────────────────────────────────
        summary_obj = telemetry.get("summary", {})
        severe_count = sum(1 for i in issues if i["severity"] == "severe")
        memory_summary = narrative[:300] + ("…" if len(narrative) > 300 else "")
        memory.record(
            scenario_id=scenario_id,
            summary=memory_summary,
            key_metrics={
                "avg_speed_kph":     summary_obj.get("avg_speed_kph", 0),
                "avg_travel_time_s": summary_obj.get("avg_travel_time_s", 0),
                "congestion_ratio":  summary_obj.get("congestion_ratio", 0),
                "severe_issues":     severe_count,
            },
        )

        return {
            "narrative":       narrative,
            "top_issues":      top_issues,
            "recommendations": recommendations,
            "memory_summary":  memory_summary,
            "model":           model_used,
        }


def _extract_recommendations(narrative: str) -> list[str]:
    """
    Heuristically extract recommendation bullet points from the narrative.
    Returns a list of strings (empty if none found).
    """
    recs = []
    for line in narrative.splitlines():
        stripped = line.strip()
        if stripped.startswith(("•", "-", "*", "→")) or (
            len(stripped) > 5 and stripped[0].isdigit() and stripped[1] in ".)"
        ):
            recs.append(stripped.lstrip("•-*→0123456789.) ").strip())
    return recs[:8]  # cap at 8
