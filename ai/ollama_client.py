"""
ai/ollama_client.py
────────────────────
Shared Ollama API client for all AI agents in the Digital Twin system.

Provides:
  - Singleton OllamaClient with configurable per-role model routing
  - Automatic retry with exponential backoff
  - Streaming and non-streaming modes
  - Health-check / availability test
  - Graceful degradation when Ollama is unreachable

Usage
─────
    from ai.ollama_client import get_ollama_client
    client = get_ollama_client()
    response = client.chat(
        messages=[{"role": "user", "content": "Analyze this traffic data..."}],
        system_prompt="You are the City Inspector Agent...",
        role="inspector",   # routes to OLLAMA_MODEL_INSPECTOR
    )
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("ollama_client")


# ── Model role registry ───────────────────────────────────────────────────────

ROLE_ENV_MAP = {
    "inspector":  "OLLAMA_MODEL_INSPECTOR",   # City Inspector narrative analysis
    "proposer":   "OLLAMA_MODEL_PROPOSER",    # Proposal generation (signal/lane/route/zoning)
    "default":    "OLLAMA_MODEL",             # Generic fallback
}

DEFAULT_MODELS = {
    "inspector":  "digital-twin-inspector",   # custom Modelfile-trained model
    "proposer":   "digital-twin-proposer",    # custom Modelfile-trained model
    "default":    "llama3.2:latest",
}


# ── Client ────────────────────────────────────────────────────────────────────

class OllamaClient:
    """
    Thread-safe Ollama HTTP client with per-role model routing.

    Parameters
    ──────────
    host          : Ollama base URL (default: OLLAMA_HOST env or http://localhost:11434)
    timeout       : Request timeout in seconds (default: OLLAMA_TIMEOUT or 120)
    max_retries   : Number of retries on transient failure (default: 2)
    retry_delay   : Base delay between retries in seconds (doubles each retry)
    """

    def __init__(
        self,
        host: str | None = None,
        timeout: int | None = None,
        max_retries: int = 1,
        retry_delay: float = 1.0,
    ):
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.timeout = int(timeout or os.getenv("OLLAMA_TIMEOUT", "45"))
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._available: bool | None = None  # cached availability

        log.info(f"OllamaClient initialized — host={self.host}, timeout={self.timeout}s")

    # ── Model resolution ──────────────────────────────────────────────────────

    def resolve_model(self, role: str = "default") -> str:
        """
        Resolve the Ollama model name for a given agent role.
        Priority: env var → custom model (if available) → llama3.2 fallback.
        """
        env_key = ROLE_ENV_MAP.get(role, ROLE_ENV_MAP["default"])
        env_val = os.getenv(env_key, "").strip()
        if env_val:
            return env_val

        # Check if the custom-trained model exists locally
        custom = DEFAULT_MODELS.get(role, DEFAULT_MODELS["default"])
        if self._model_exists(custom):
            return custom

        # Fallback to base llama3.2
        fallback = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
        log.debug(f"Role '{role}': custom model '{custom}' not found — using fallback '{fallback}'")
        return fallback

    def _model_exists(self, model_name: str) -> bool:
        """Check whether a model is available in the local Ollama registry."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                # Support partial match (e.g. "llama3.2" matches "llama3.2:latest")
                return any(model_name in m or m.startswith(model_name) for m in models)
        except Exception:
            pass
        return False

    # ── Availability ──────────────────────────────────────────────────────────

    def is_available(self, force_check: bool = False) -> bool:
        """Return True if Ollama is reachable. Result is cached after first check."""
        if self._available is not None and not force_check:
            return self._available
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            self._available = resp.status_code == 200
        except Exception as e:
            log.warning(f"Ollama not reachable at {self.host}: {e}")
            self._available = False
        return self._available

    def list_models(self) -> list[str]:
        """Return list of locally available model names."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception as e:
            log.warning(f"Could not list Ollama models: {e}")
        return []

    # ── Core chat call ────────────────────────────────────────────────────────

    def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        role: str = "default",
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        stream: bool = False,
        timeout: int | float | None = None,
        retries: int | None = None,
    ) -> str:
        """
        Send a chat request to Ollama and return the response text.

        Parameters
        ──────────
        messages      : List of {"role": ..., "content": ...} dicts.
        system_prompt : System message prepended to the conversation.
        role          : Agent role key for model routing ("inspector", "proposer", etc.).
        model         : Override model name (skips role routing if set).
        temperature   : Sampling temperature (0.0–1.0).
        max_tokens    : Max tokens in response (None = model default).
        stream        : If True, streams and collects chunks.
        timeout       : Custom timeout in seconds (overrides client default).
        retries       : Custom retry count (overrides client default).

        Returns
        ───────
        Response text string, or raises RuntimeError on failure.
        """
        target_model = model or self.resolve_model(role)
        url = f"{self.host}/api/chat"

        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload: dict[str, Any] = {
            "model":   target_model,
            "messages": full_messages,
            "stream":  stream,
            "options": {"temperature": temperature},
        }
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        req_timeout = timeout if timeout is not None else self.timeout
        max_attempts = (retries if retries is not None else self.max_retries) + 1

        last_exc: Exception | None = None
        for attempt in range(max_attempts):
            try:
                resp = requests.post(url, json=payload, timeout=req_timeout, stream=stream)
                resp.raise_for_status()

                if stream:
                    return self._collect_stream(resp)
                else:
                    return resp.json()["message"]["content"]

            except requests.exceptions.Timeout as e:
                log.warning(f"Ollama timeout on attempt {attempt + 1}/{max_attempts}: {e}")
                last_exc = e
            except requests.exceptions.RequestException as e:
                log.warning(f"Ollama request error on attempt {attempt + 1}/{max_attempts}: {e}")
                last_exc = e
            except (KeyError, ValueError) as e:
                log.error(f"Unexpected Ollama response format: {e}")
                raise RuntimeError(f"Ollama response parse error: {e}") from e

            if attempt < max_attempts - 1:
                delay = self.retry_delay * (2 ** attempt)
                log.info(f"Retrying in {delay:.1f}s...")
                time.sleep(delay)

        raise RuntimeError(f"Ollama call failed after {max_attempts} attempts: {last_exc}")

    def _collect_stream(self, resp: requests.Response) -> str:
        """Collect streamed response chunks into a single string."""
        parts = []
        for line in resp.iter_lines():
            if line:
                try:
                    import json
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        parts.append(content)
                    if chunk.get("done"):
                        break
                except Exception:
                    continue
        return "".join(parts)

    # ── Convenience wrappers ──────────────────────────────────────────────────

    def generate(self, prompt: str, role: str = "default", system: str = "", **kwargs) -> str:
        """Simple single-turn generation."""
        return self.chat(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system,
            role=role,
            **kwargs,
        )


# ── Singleton ──────────────────────────────────────────────────────────────────

_client_instance: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    """Return the global OllamaClient singleton."""
    global _client_instance
    if _client_instance is None:
        _client_instance = OllamaClient()
    return _client_instance

