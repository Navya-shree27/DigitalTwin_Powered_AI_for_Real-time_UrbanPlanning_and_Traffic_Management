"""
agents/multi_agent_framework.py
───────────────────────────────
Base infrastructure for Ollama-driven multi-agent AI system.

Provides:
  - Configurable Ollama API client (OLLAMA_HOST, OLLAMA_MODEL).
  - Robust prompt formatting with structured schema enforcement.
  - Graceful deterministic fallback when Ollama is offline or unreachable.
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("multi_agent_framework")


class OllamaClient:
    """
    HTTP client for local Ollama inference with timeout and fallback handling.
    """

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout_s: int = 120,
    ):
        self.host = (
            host
            or os.getenv("OLLAMA_HOST")
            or os.getenv("OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434"
        ).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL") or "llama3.2:3b"
        self.timeout_s = timeout_s
        self._is_available: bool | None = None

    def is_available(self, force_check: bool = False) -> bool:
        """Check if local Ollama daemon is reachable."""
        if self._is_available is not None and not force_check:
            return self._is_available

        try:
            res = requests.get(f"{self.host}/api/tags", timeout=2)
            self._is_available = (res.status_code == 200)
        except Exception:
            self._is_available = False

        return self._is_available

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        format_json: bool = False,
    ) -> str:
        """
        Send chat prompt to Ollama and return response string.
        """
        url = f"{self.host}/api/chat"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }
        if format_json:
            payload["format"] = "json"

        try:
            res = requests.post(url, json=payload, timeout=self.timeout_s)
            res.raise_for_status()
            data = res.json()
            return data.get("message", {}).get("content", "").strip()
        except Exception as e:
            log.warning(f"Ollama request to {url} failed: {e}. Falling back to analytical reasoning.")
            raise RuntimeError(f"Ollama inference error: {e}") from e


class BaseAgent(ABC):
    """
    Abstract base class for all intelligent agents.
    """

    def __init__(self, client: OllamaClient | None = None, role_name: str = "BaseAgent"):
        self.client = client or OllamaClient()
        self.role_name = role_name

    @abstractmethod
    def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute agent analysis cycle."""
        pass

    def _call_llm_or_fallback(
        self,
        system_prompt: str,
        user_prompt: str,
        fallback_func,
        context: dict[str, Any],
        format_json: bool = False,
    ) -> Any:
        """
        Executes Ollama inference if online, otherwise runs deterministic analytical fallback.
        """
        try:
            if self.client.is_available():
                response = self.client.chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    format_json=format_json,
                )
                if format_json:
                    # Parse JSON from response
                    try:
                        return json.loads(response)
                    except json.JSONDecodeError:
                        # Extract JSON with regex if markdown backticks are present
                        match = re.search(r"\{.*\}", response, re.DOTALL)
                        if match:
                            return json.loads(match.group(0))
                        return fallback_func(context)
                return response
        except Exception as e:
            log.info(f"Agent '{self.role_name}' running deterministic fallback: {e}")

        return fallback_func(context)
