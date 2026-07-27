#!/usr/bin/env bash
# scripts/setup.sh
# ────────────────
# Automatic setup script for the Traffic Digital Twin Sandbox.

echo "=================================================="
echo "Starting Traffic Digital Twin Sandbox Environment Setup"
echo "=================================================="

# ── 1. Dependency Checks ──────────────────────────────────────────────────────

# Check Python
if command -v python3 &>/dev/null; then
    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo "✔ Found Python 3: version $PYTHON_VERSION"
else
    echo "❌ Python 3 is not installed. Please install Python 3.11+"
    exit 1
fi

# Check Node.js
if command -v node &>/dev/null; then
    NODE_VERSION=$(node -v)
    echo "✔ Found Node.js: version $NODE_VERSION"
else
    echo "⚠️  Node.js is not installed. Frontend setup will be skipped."
fi

# Check SUMO
if command -v sumo &>/dev/null; then
    SUMO_BIN=$(which sumo)
    echo "✔ Found SUMO installation: $SUMO_BIN"
    if [ -z "$SUMO_HOME" ]; then
        echo "⚠️  SUMO_HOME environment variable is not set. Setting it dynamically..."
        export SUMO_HOME=$(dirname "$(dirname "$SUMO_BIN")")
        echo "   SUMO_HOME is set to: $SUMO_HOME"
    else
        echo "✔ SUMO_HOME: $SUMO_HOME"
    fi
else
    echo "❌ SUMO is not installed or not in PATH. Please install SUMO to run simulations."
fi

# Check Docker
if command -v docker &>/dev/null; then
    echo "✔ Found Docker"
else
    echo "⚠️  Docker is not installed. You will not be able to deploy via containers."
fi

# ── 2. Environment Configurations ─────────────────────────────────────────────

if [ ! -f .env ]; then
    echo "Configuring .env file from .env.example..."
    cp .env.example .env
fi

# ── 3. Python Virtual Env & Packages ─────────────────────────────────────────

echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
echo "Installing Python dependencies (requirements.txt)..."
pip install -r requirements.txt

# ── 4. Frontend Package Setup ──────────────────────────────────────────────────

if command -v npm &>/dev/null; then
    echo "Installing frontend dependencies..."
    cd frontend && npm install && cd ..
fi

echo "=================================================="
echo "Setup Completed Successfully!"
echo "To start the backend: source venv/bin/activate && uvicorn backend.app:app --reload"
echo "To start the frontend: cd frontend && npm run dev"
echo "=================================================="
