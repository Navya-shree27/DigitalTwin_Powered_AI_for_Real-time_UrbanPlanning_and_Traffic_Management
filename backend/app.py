"""
backend/app.py
───────────────
FastAPI application entry point.

Start with:
    cd d:/major_project
    uvicorn backend.app:app --reload --port 8000

API docs available at: http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# ── Path setup ────────────────────────────────────────────────────────────────
# Make the project root importable regardless of CWD
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.database.db_connector import init_db
from backend.api.routes_simulation import router as simulation_router
from backend.api.routes_agents import router as agents_router
from backend.api.routes_dashboard import router as dashboard_router

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("app")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Digital Twin Traffic AI",
    description=(
        "Real-time urban planning and traffic management system powered by "
        "OpenStreetMap, AI agents, and traffic simulation."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(simulation_router)
app.include_router(agents_router)
app.include_router(dashboard_router)


# ── Startup ───────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup() -> None:
    log.info("Digital Twin Traffic AI backend starting …")
    init_db()
    log.info("Database ready.")
    log.info("API docs: http://localhost:8000/docs")


@app.get("/health", tags=["System"])
def health() -> dict:
    import shutil
    import sys
    
    traci_import = False
    traci_error = None
    try:
        import traci
        traci_import = True
    except Exception as e:
        traci_error = str(e)
        
    osmnx_import = False
    osmnx_error = None
    try:
        import osmnx as ox
        osmnx_import = True
    except Exception as e:
        osmnx_error = str(e)
        
    sumo_bin = shutil.which("sumo")
    sumo_gui_bin = shutil.which("sumo-gui")
    
    # Query database runs
    from backend.database.db_connector import SessionLocal
    from backend.models.schema import SimulationRun
    db = SessionLocal()
    runs_info = []
    try:
        runs = db.query(SimulationRun).order_by(SimulationRun.id.desc()).limit(5).all()
        for r in runs:
            runs_info.append({
                "id": r.id,
                "scenario_id": r.scenario_id,
                "status": r.status,
                "engine": r.engine,
                "duration_s": r.duration_s,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "has_telemetry": r.telemetry_json is not None,
                "avg_travel_time": r.avg_travel_time_s
            })
    except Exception as e:
        runs_info = f"Query error: {e}"
    finally:
        db.close()
    
    return {
        "status": "ok",
        "service": "digital-twin-traffic-ai",
        "python_version": sys.version,
        "traci_available": traci_import,
        "traci_error": traci_error,
        "osmnx_available": osmnx_import,
        "osmnx_error": osmnx_error,
        "sumo_path": sumo_bin,
        "sumo_gui_path": sumo_gui_bin,
        "sumo_home_env": os.environ.get("SUMO_HOME"),
        "recent_runs": runs_info
    }


@app.get("/", tags=["System"])
def root() -> dict:
    return {
        "message": "Digital Twin Traffic AI — API running.",
        "docs":    "http://localhost:8000/docs",
        "version": "0.1.0",
    }
