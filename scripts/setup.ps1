# scripts/setup.ps1
# ──────────────────
# PowerShell setup script for Windows.

Write-Host "==================================================" -ForegroundColor Green
Write-Host "Starting Traffic Digital Twin Sandbox Environment Setup" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

# ── 1. Dependency Checks ──────────────────────────────────────────────────────

# Check Python
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($python) {
    $version = python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'
    Write-Host "✔ Found Python: version $version" -ForegroundColor Cyan
} else {
    Write-Host "❌ Python is not installed. Please install Python 3.11+" -ForegroundColor Red
    Exit
}

# Check Node.js
$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    $nodeVersion = node -v
    Write-Host "✔ Found Node.js: version $nodeVersion" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  Node.js is not installed. Frontend setup will be skipped." -ForegroundColor Yellow
}

# Check SUMO
$sumo = Get-Command sumo -ErrorAction SilentlyContinue
if ($sumo) {
    Write-Host "✔ Found SUMO installation: $($sumo.Source)" -ForegroundColor Cyan
    if ([string]::IsNullOrEmpty($env:SUMO_HOME)) {
        Write-Host "⚠️  SUMO_HOME environment variable is not set. Please set it to your SUMO install directory." -ForegroundColor Yellow
    } else {
        Write-Host "✔ SUMO_HOME: $env:SUMO_HOME" -ForegroundColor Cyan
    }
} else {
    Write-Host "❌ SUMO is not installed. Please install SUMO to run simulations." -ForegroundColor Red
}

# Check Docker
$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    Write-Host "✔ Found Docker" -ForegroundColor Cyan
} else {
    Write-Host "⚠️  Docker is not installed. You will not be able to deploy via containers." -ForegroundColor Yellow
}

# ── 2. Environment Configurations ─────────────────────────────────────────────

if (!(Test-Path .env)) {
    Write-Host "Configuring .env file from .env.example..." -ForegroundColor Gray
    Copy-Item .env.example .env
}

# ── 3. Python Virtual Env & Packages ─────────────────────────────────────────

Write-Host "Setting up Python virtual environment..." -ForegroundColor Gray
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
Write-Host "Installing Python dependencies (requirements.txt)..." -ForegroundColor Gray
pip install -r requirements.txt

# ── 4. Frontend Package Setup ──────────────────────────────────────────────────

if ($node) {
    Write-Host "Installing frontend dependencies..." -ForegroundColor Gray
    Set-Location frontend
    npm install
    Set-Location ..
}

Write-Host "==================================================" -ForegroundColor Green
Write-Host "Setup Completed Successfully!" -ForegroundColor Green
Write-Host "To start the backend: .\venv\Scripts\Activate.ps1; uvicorn backend.app:app --reload" -ForegroundColor Cyan
Write-Host "To start the frontend: cd frontend; npm run dev" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Green
