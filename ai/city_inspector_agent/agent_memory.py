"""
ai/city_inspector_agent/agent_memory.py
────────────────────────────────────────────
Short-term memory store for the City Inspector Agent.

Persists analysis cycle summaries so the LLM can reason about whether
conditions have improved or deteriorated compared to prior runs.

Storage
───────
  • In-process: Python dict keyed by scenario_id
  • On-disk:    JSON file at data/processed/agent_memory.json
                (auto-loaded on first use)

Schema per entry
────────────────
  {
    "scenario_id": int,
    "cycle":       int,        # monotonically increasing cycle counter
    "timestamp":   str,        # ISO 8601
    "summary":     str,        # LLM-generated memory summary
    "key_metrics": {
      "avg_speed_kph":      float,
      "avg_travel_time_s":  float,
      "congestion_ratio":   float,
      "severe_issues":      int,
    }
  }
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY_FILE = ROOT / "data" / "processed" / "agent_memory.json"
MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)

log = logging.getLogger("agent_memory")


class AgentMemory:
    """
    Thread-safe (single-process) in-memory + file-backed store for
    the City Inspector Agent's analysis history.
    """

    def __init__(self, max_cycles_per_scenario: int = 10):
        self._max_cycles = max_cycles_per_scenario
        self._store: dict[int, list[dict]] = {}   # scenario_id → [entries]
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        if MEMORY_FILE.exists():
            try:
                raw = json.loads(MEMORY_FILE.read_text())
                # Convert string keys back to ints
                self._store = {int(k): v for k, v in raw.items()}
                total = sum(len(v) for v in self._store.values())
                log.info(f"Loaded agent memory: {len(self._store)} scenarios, {total} cycles.")
            except Exception as e:
                log.warning(f"Could not load agent memory: {e}. Starting fresh.")
                self._store = {}

    def _save(self) -> None:
        try:
            MEMORY_FILE.write_text(json.dumps(self._store, indent=2))
        except Exception as e:
            log.warning(f"Could not save agent memory: {e}")

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_latest(self, scenario_id: int) -> dict | None:
        """Return the most recent memory entry for a scenario, or None."""
        entries = self._store.get(scenario_id, [])
        return entries[-1] if entries else None

    def get_all(self, scenario_id: int) -> list[dict]:
        """Return all memory entries for a scenario (oldest first)."""
        return list(self._store.get(scenario_id, []))

    def get_prior_summary(self, scenario_id: int) -> str:
        """Return a text summary suitable for injection into the LLM prompt."""
        latest = self.get_latest(scenario_id)
        if latest is None:
            return "No prior analysis cycles available for this scenario."
        return (
            f"[Cycle {latest['cycle']} — {latest['timestamp']}]\n"
            f"{latest.get('summary', 'No summary available.')}\n"
            f"Key metrics: speed={latest['key_metrics'].get('avg_speed_kph', 'N/A')} km/h, "
            f"travel_time={latest['key_metrics'].get('avg_travel_time_s', 'N/A')}s, "
            f"congestion={latest['key_metrics'].get('congestion_ratio', 'N/A'):.1%}, "
            f"severe_issues={latest['key_metrics'].get('severe_issues', 'N/A')}."
        )

    # ── Write ─────────────────────────────────────────────────────────────────

    def record(
        self,
        scenario_id: int,
        summary: str,
        key_metrics: dict,
    ) -> dict:
        """
        Add a new memory entry for *scenario_id*.
        Returns the new entry.
        """
        entries = self._store.setdefault(scenario_id, [])
        cycle   = (entries[-1]["cycle"] + 1) if entries else 1

        entry = {
            "scenario_id": scenario_id,
            "cycle":       cycle,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
            "summary":     summary,
            "key_metrics": key_metrics,
        }
        entries.append(entry)

        # Trim old entries
        if len(entries) > self._max_cycles:
            self._store[scenario_id] = entries[-self._max_cycles:]

        self._save()
        log.info(f"Memory recorded: scenario={scenario_id}, cycle={cycle}.")
        return entry

    def clear(self, scenario_id: int | None = None) -> None:
        """Clear memory for a specific scenario or all scenarios."""
        if scenario_id is not None:
            self._store.pop(scenario_id, None)
        else:
            self._store.clear()
        self._save()
        log.info(f"Memory cleared: scenario={scenario_id or 'ALL'}.")


# ── Singleton ─────────────────────────────────────────────────────────────────
_memory_instance: AgentMemory | None = None


def get_memory() -> AgentMemory:
    """Return the process-wide AgentMemory singleton."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = AgentMemory()
    return _memory_instance
