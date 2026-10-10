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


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health() -> dict:
    return {"status": "ok", "service": "digital-twin-traffic-ai"}


@app.get("/", tags=["System"])
def root() -> dict:
    return {
        "message": "Digital Twin Traffic AI — API running.",
        "docs":    "http://localhost:8000/docs",
        "version": "0.1.0",
    }
