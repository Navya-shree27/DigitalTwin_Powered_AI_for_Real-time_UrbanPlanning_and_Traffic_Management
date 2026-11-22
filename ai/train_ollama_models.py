"""
ai/train_ollama_models.py
--------------------------
Creates custom Ollama models from Modelfiles for the Digital Twin project.

This script:
  1. Verifies Ollama is running and the base model (llama3.2) is available
  2. Creates `digital-twin-inspector` from Modelfile.inspector
  3. Creates `digital-twin-proposer` from Modelfile.proposer
  4. Runs quick smoke-test prompts to verify each model works
  5. Updates .env to point to the custom model names

Usage
-----
    # From project root:
    python -m ai.train_ollama_models

    # Force recreate even if models already exist:
    python -m ai.train_ollama_models --force

    # Test only (no creation):
    python -m ai.train_ollama_models --test-only
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
MODELFILES_DIR = ROOT / "ai" / "training_data" / "modelfiles"
ENV_FILE = ROOT / ".env"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("train_ollama")

# -- Model definitions ---------------------------------------------------------

MODELS = [
    {
        "name":        "digital-twin-inspector",
        "modelfile":   MODELFILES_DIR / "Modelfile.inspector",
        "env_key":     "OLLAMA_MODEL_INSPECTOR",
        "description": "City Inspector Agent - traffic analysis and narrative generation",
        "test_prompt": (
            "Quick test: What is the network health if average speed is 15 km/h "
            "and congestion ratio is 35%? Give a 1-sentence assessment."
        ),
    },
    {
        "name":        "digital-twin-proposer",
        "modelfile":   MODELFILES_DIR / "Modelfile.proposer",
        "env_key":     "OLLAMA_MODEL_PROPOSER",
        "description": "Proposal Generator Agent - structured intervention proposals",
        "test_prompt": (
            "Issue: severe congestion on a primary road, occupancy 90%, widenable=True. "
            "Respond with a JSON proposal (proposal_type, title, rationale only - keep it short)."
        ),
    },
]

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


# -- Helpers -------------------------------------------------------------------

def check_ollama_running() -> bool:
    """Check if Ollama is reachable."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def list_local_models() -> list[str]:
    """Return names of locally available Ollama models."""
    try:
        r = requests.get(f"{OLLAMA_HOST}/api/tags", timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def model_exists(name: str) -> bool:
    """Check if a model (or its :latest variant) exists locally."""
    models = list_local_models()
    return any(name in m or m.startswith(name) for m in models)


def create_model(name: str, modelfile_path: Path) -> bool:
    """
    Create an Ollama model from a Modelfile via CLI or REST API.
    Returns True on success, False on failure.
    """
    if not modelfile_path.exists():
        log.error(f"Modelfile not found: {modelfile_path}")
        return False

    log.info(f"Creating model '{name}' from {modelfile_path.name}...")

    # Primary method: use ollama CLI
    try:
        proc = subprocess.run(
            ["ollama", "create", name, "-f", str(modelfile_path)],
            capture_output=True,
            text=True,
            check=False,
            shell=True,
        )
        if model_exists(name):
            log.info(f"[OK] Model '{name}' created successfully via CLI.")
            return True
        else:
            log.warning(f"CLI creation returned code {proc.returncode}. Output: {proc.stdout} {proc.stderr}")
    except Exception as e:
        log.warning(f"CLI creation error: {e}. Trying REST API fallback...")

    # Fallback method: REST API
    modelfile_content = modelfile_path.read_text(encoding="utf-8")
    url = f"{OLLAMA_HOST}/api/create"
    payload = {
        "name":      name,
        "modelfile": modelfile_content,
        "stream":    False,
    }

    try:
        resp = requests.post(url, json=payload, timeout=300)
        resp.raise_for_status()
        if model_exists(name):
            log.info(f"[OK] Model '{name}' created successfully via API.")
            return True
        return False
    except Exception as e:
        log.error(f"Failed to create model '{name}': {e}")
        return False


def test_model(name: str, prompt: str) -> bool:
    """Run a quick smoke test against a model. Returns True if response is non-empty."""
    log.info(f"Testing model '{name}'...")
    url = f"{OLLAMA_HOST}/api/chat"
    payload = {
        "model": name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 150},
    }
    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        if content.strip():
            log.info(f"[OK] Model '{name}' smoke test passed.")
            log.info(f"  Sample response: {content[:200]}...")
            return True
        else:
            log.warning(f"[FAIL] Model '{name}' returned empty response.")
            return False
    except Exception as e:
        log.error(f"[ERR] Smoke test failed for '{name}': {e}")
        return False


def update_env(key: str, value: str):
    """Update or add a key=value line in the .env file."""
    if not ENV_FILE.exists():
        log.warning(f".env file not found at {ENV_FILE} - skipping env update.")
        return

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    updated = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
            new_lines.append(f"{key}={value}")
            updated = True
        else:
            new_lines.append(line)

    if not updated:
        new_lines.append(f"{key}={value}")

    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    log.info(f"Updated .env: {key}={value}")


# -- Main ----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Create and test custom Ollama models for the Digital Twin system."
    )
    parser.add_argument("--force", action="store_true", help="Recreate models even if they exist")
    parser.add_argument("--test-only", action="store_true", help="Only run smoke tests, no creation")
    parser.add_argument("--model", type=str, help="Only process a specific model by name")
    args = parser.parse_args()

    print("\n" + "="*60)
    print(" Digital Twin - Ollama Model Training")
    print("="*60 + "\n")

    # -- 1. Check Ollama -------------------------------------------------------
    if not check_ollama_running():
        log.error(
            f"Ollama is not running or not reachable at {OLLAMA_HOST}.\n"
            "  Start Ollama with: ollama serve\n"
            "  Then re-run this script."
        )
        sys.exit(1)

    log.info(f"[OK] Ollama is running at {OLLAMA_HOST}")
    available = list_local_models()
    log.info(f"  Available models: {available}")

    # -- 2. Check base model ---------------------------------------------------
    base_model = "llama3.2:latest"
    if not model_exists(base_model.split(":")[0]):
        log.error(
            f"Base model '{base_model}' not found locally.\n"
            f"  Pull it first: ollama pull {base_model}"
        )
        sys.exit(1)
    log.info(f"[OK] Base model '{base_model}' is available.")

    # -- 3. Process each model -------------------------------------------------
    results = {}
    for model_def in MODELS:
        name = model_def["name"]
        if args.model and args.model != name:
            continue

        print(f"\n-- {name} ------------------------------------------")
        print(f"   {model_def['description']}")

        if not args.test_only:
            if model_exists(name) and not args.force:
                log.info(f"Model '{name}' already exists. Use --force to recreate.")
            else:
                if model_exists(name) and args.force:
                    log.info(f"Recreating model '{name}' (--force)...")
                success = create_model(name, model_def["modelfile"])
                if not success:
                    log.error(f"Failed to create '{name}'. Check modelfile and Ollama logs.")
                    results[name] = "FAILED"
                    continue

            # Update .env
            update_env(model_def["env_key"], name)

        # Smoke test
        test_ok = test_model(name, model_def["test_prompt"])
        results[name] = "PASS" if test_ok else "FAIL"

    # -- 4. Summary ------------------------------------------------------------
    print("\n" + "="*60)
    print(" Results")
    print("="*60)
    for model_name, status in results.items():
        icon = "[PASS]" if status == "PASS" else "[FAIL]"
        print(f"  {icon} {model_name}: {status}")

    print("\n")
    if all(v == "PASS" for v in results.values()):
        print("All models ready! The Digital Twin AI agents will now use:")
        print(f"  Inspector: digital-twin-inspector (via OLLAMA_MODEL_INSPECTOR)")
        print(f"  Proposer:  digital-twin-proposer  (via OLLAMA_MODEL_PROPOSER)")
        print(f"\nSet LLM_PROVIDER=ollama in your .env to activate Ollama mode.")
    else:
        print("Some models failed. Check logs above. Fallback to llama3.2:latest will be used.")
    print()


if __name__ == "__main__":
    main()
