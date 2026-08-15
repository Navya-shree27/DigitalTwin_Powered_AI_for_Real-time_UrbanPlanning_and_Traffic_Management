"""
scripts/reset_db.py
───────────────────
Clears the SQLite database (digital_twin.db) and any temporary progress/report caches,
then re-initializes clean database tables.
"""

import logging
import os
import shutil
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("reset_db")

ROOT = Path(__file__).resolve().parent.parent

def reset():
    log.info("Resetting Digital Twin Database and cached telemetry...")

    # 1. Delete digital_twin.db
    db_file = ROOT / "digital_twin.db"
    if db_file.exists():
        try:
            db_file.unlink()
            log.info("✔ Deleted digital_twin.db")
        except Exception as e:
            log.error(f"Failed to delete digital_twin.db: {e}")

    # 2. Clear progress_*.json files in data/
    data_dir = ROOT / "data"
    if data_dir.exists():
        for pf in data_dir.glob("progress_*.json"):
            try:
                pf.unlink()
                log.info(f"✔ Deleted stale progress file: {pf.name}")
            except Exception:
                pass

    # 3. Clear report JSONs in data/processed/reports/
    reports_json_dir = ROOT / "data" / "processed" / "reports"
    if reports_json_dir.exists():
        for rf in reports_json_dir.glob("*.json"):
            try:
                rf.unlink()
            except Exception:
                pass
        log.info("✔ Cleared processed JSON reports directory.")

    # 4. Re-initialize database tables
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from backend.database.db_connector import init_db
    init_db()
    log.info("✔ Database successfully re-initialized with fresh tables!")

if __name__ == "__main__":
    reset()
