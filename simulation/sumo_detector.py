"""
simulation/sumo_detector.py
───────────────────────────
Detects whether SUMO is installed on the host machine and returns the
absolute paths to the SUMO and netconvert binaries.

Detection order
───────────────
1. SUMO_HOME environment variable (from .env or system).
2. PATH lookup via shutil.which() for 'sumo' / 'sumo.exe' / 'netconvert'.
3. Common install directories (Windows: Program Files, Linux: /usr/bin).

The result is cached per-process — detection runs at most once.

Usage
─────
    from simulation.sumo_detector import detect_sumo
    info = detect_sumo()
    if info["available"]:
        sumo_bin = info["sumo_bin"]
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger("sumo_detector")

ROOT = Path(__file__).resolve().parent.parent

# Module-level cache — populated on first call
_CACHE: dict | None = None

# Common install locations to probe when SUMO_HOME is not set
_WINDOWS_HINTS = [
    r"C:\Program Files (x86)\Eclipse\Sumo",
    r"C:\Program Files\Eclipse\Sumo",
    r"C:\sumo",
    r"D:\sumo",
]
_LINUX_HINTS = [
    "/usr/bin",
    "/usr/local/bin",
    "/opt/sumo/bin",
]


def detect_sumo(force: bool = False) -> dict:
    """
    Probe the system for a working SUMO installation.

    Parameters
    ──────────
    force : Re-run detection even if the cache is populated.

    Returns
    ───────
    {
      "available":      bool,
      "sumo_bin":       str | None,        # absolute path
      "netconvert_bin": str | None,
      "sumo_home":      str | None,
      "version":        str | None,        # e.g. "1.19.0"
      "traci_available": bool,
    }
    """
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    result: dict = {
        "available":       False,
        "sumo_bin":        None,
        "netconvert_bin":  None,
        "sumo_home":       None,
        "version":         None,
        "traci_available": False,
    }

    # ── 1. Check TraCI Python package ────────────────────────────────────────
    try:
        import traci  # type: ignore
        result["traci_available"] = True
    except ImportError:
        log.info("TraCI Python package not found (pip install eclipse-sumo or traci).")

    # ── 2. Determine SUMO_HOME ────────────────────────────────────────────────
    sumo_home = os.environ.get("SUMO_HOME", "").strip()
    if sumo_home and Path(sumo_home).is_dir():
        log.info(f"SUMO_HOME from env: {sumo_home}")
        result["sumo_home"] = sumo_home
        _sumo_bin, _net_bin = _bins_from_home(sumo_home)
    else:
        _sumo_bin, _net_bin = None, None

    # ── 3. PATH lookup ────────────────────────────────────────────────────────
    if _sumo_bin is None:
        _sumo_bin = _which_sumo()
    if _net_bin is None:
        _net_bin = _which_netconvert()

    # ── 4. Hint directories ───────────────────────────────────────────────────
    if _sumo_bin is None:
        hints = _WINDOWS_HINTS if os.name == "nt" else _LINUX_HINTS
        for hint in hints:
            hpath = Path(hint)
            if not hpath.is_dir():
                continue
            s, n = _bins_from_home(str(hpath))
            if s:
                _sumo_bin = s
                _net_bin  = n or _net_bin
                if result["sumo_home"] is None:
                    result["sumo_home"] = str(hpath)
                break

    if _sumo_bin is None:
        log.warning(
            "SUMO binary not found. "
            "Set SUMO_HOME in .env or install SUMO: https://sumo.dlr.de/docs/Downloads.php"
        )
        _CACHE = result
        return result

    # ── 5. Verify binary works ────────────────────────────────────────────────
    version = _probe_version(_sumo_bin)
    if version is None:
        log.warning(f"SUMO binary found at {_sumo_bin} but '--version' failed.")
        _CACHE = result
        return result

    result["available"]      = True
    result["sumo_bin"]       = str(_sumo_bin)
    result["netconvert_bin"] = str(_net_bin) if _net_bin else None
    result["version"]        = version
    log.info(f"SUMO detected: version={version}, bin={_sumo_bin}")

    _CACHE = result
    return result


# ── Private helpers ───────────────────────────────────────────────────────────

def _bins_from_home(home: str):
    """Return (sumo_bin, netconvert_bin) given a SUMO_HOME directory."""
    bin_dir = Path(home) / "bin"
    sumo_candidates = ["sumo.exe", "sumo"]
    net_candidates  = ["netconvert.exe", "netconvert"]

    sumo_bin = None
    for c in sumo_candidates:
        p = bin_dir / c
        if p.exists():
            sumo_bin = p
            break

    net_bin = None
    for c in net_candidates:
        p = bin_dir / c
        if p.exists():
            net_bin = p
            break

    return sumo_bin, net_bin


def _which_sumo():
    for name in ("sumo", "sumo.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _which_netconvert():
    for name in ("netconvert", "netconvert.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _probe_version(sumo_bin) -> str | None:
    """Run `sumo --version` and extract the version string."""
    try:
        result = subprocess.run(
            [str(sumo_bin), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout + result.stderr
        for line in output.splitlines():
            line = line.strip()
            # Version line looks like: "SUMO sumo Version 1.19.0"
            if "version" in line.lower() or "sumo" in line.lower():
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.lower() in ("version", "v") and i + 1 < len(parts):
                        return parts[i + 1].strip(",")
                # Fallback: return the whole first meaningful line
                if line:
                    return line[:60]
        return "unknown"
    except Exception as exc:
        log.debug(f"SUMO version probe failed: {exc}")
        return None
