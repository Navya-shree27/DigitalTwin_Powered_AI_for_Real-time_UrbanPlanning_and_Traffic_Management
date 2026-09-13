"""
backend/api/routes_status.py
──────────────────────────────
System health endpoint.

GET /api/status
───────────────
Returns the availability of optional external dependencies:
  - SUMO binary (for live simulation)
  - TraCI Python package
  - LLM provider (Anthropic / Ollama)
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter

log = logging.getLogger("routes_status")
router = APIRouter(tags=["System"])


@router.get("/api/status")
def get_status() -> dict:
    """
    Returns system-level dependency status.

    Used by the dashboard to display the 🟢 SUMO Live / 🟡 Synthetic chip
    and to show which simulation engines are available.
    """
    # ── SUMO detection ────────────────────────────────────────────────────────
    try:
        from simulation.sumo_detector import detect_sumo
        sumo_info = detect_sumo()
    except Exception as e:
        log.warning(f"SUMO detection error: {e}")
        sumo_info = {"available": False, "sumo_bin": None, "version": None, "traci_available": False}

    # ── LLM provider check ────────────────────────────────────────────────────
    llm_provider = "none"
    llm_available = False

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    ollama_url    = os.getenv("OLLAMA_BASE_URL",   "").strip()

    if anthropic_key and anthropic_key not in ("", "your_anthropic_api_key_here"):
        llm_provider  = "anthropic"
        llm_available = True
    elif ollama_url:
        llm_provider  = "ollama"
        llm_available = True

    return {
        "sumo": {
            "available":       sumo_info.get("available", False),
            "version":         sumo_info.get("version"),
            "bin":             sumo_info.get("sumo_bin"),
            "netconvert_bin":  sumo_info.get("netconvert_bin"),
            "sumo_home":       sumo_info.get("sumo_home"),
        },
        "traci": {
            "available": sumo_info.get("traci_available", False),
        },
        "llm": {
            "provider":  llm_provider,
            "available": llm_available,
        },
        "engines": {
            "synthetic": True,          # always available
            "sumo":      sumo_info.get("available", False),
            "cityflow":  False,         # Phase B+
        },
    }
