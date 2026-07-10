"""
backend/database/db_connector.py
──────────────────────────────────
Database connection factory.

Uses SQLAlchemy with SQLite by default.
Swap DATABASE_URL in .env for PostgreSQL + PostGIS in Phase B+.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT / ".env")

log = logging.getLogger("db_connector")

DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'digital_twin.db'}")

# SQLite: allow check_same_thread=False so FastAPI can use it in async context
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yield a DB session and close it on exit."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables defined in schema.py (idempotent)."""
    from backend.models import schema  # noqa: F401 — ensures models are registered
    from sqlalchemy import inspect, text
    Base.metadata.create_all(bind=engine)
    log.info(f"Database initialised: {DATABASE_URL}")

    # Auto-migration: check if noise_pollution_db exists in simulation_runs, add it if not
    try:
        inspector = inspect(engine)
        if "simulation_runs" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("simulation_runs")]
            if columns and "noise_pollution_db" not in columns:
                log.info("Migration: Adding noise_pollution_db column to simulation_runs table...")
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE simulation_runs ADD COLUMN noise_pollution_db FLOAT"))
            if columns and "agent_narrative" not in columns:
                log.info("Migration: Adding agent_narrative column to simulation_runs table...")
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE simulation_runs ADD COLUMN agent_narrative TEXT"))
    except Exception as e:
        log.warning(f"Failed to auto-migrate simulation_runs: {e}")

    # Reset any stuck "running" or "pending" runs from previous crashes
    try:
        db = SessionLocal()
        stuck_runs = (
            db.query(schema.SimulationRun)
            .filter(schema.SimulationRun.status.in_(["running", "pending"]))
            .all()
        )
        if stuck_runs:
            log.info(f"Cleaning up {len(stuck_runs)} stuck simulation runs from previous session...")
            for run in stuck_runs:
                run.status = "failed"
            db.commit()
    except Exception as e:
        log.warning(f"Failed to reset stuck runs: {e}")
    finally:
        db.close()
