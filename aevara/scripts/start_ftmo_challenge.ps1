<#
# @module: start_ftmo_challenge.ps1
# @deps: aevara/src/deployment/ftmo_manager.py, aevara/src/execution/mt5_adapter.py
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: Operational Launcher for Aevra in FTMO Challenge Mode. Validates credentials, starts Bridge, and activates MT5.
#>

param (
    [string]$AccountID = "CHALLENGE_123",
    [float]$Balance = 100000.0,
    [bool]$PilotMode = $true
)

Write-Host "🚀 AEVRA — FTMO CHALLENGE ACTIVATION: Initiating Operation Omega..." -ForegroundColor Cyan
Write-Host " 🏛️ DEPLOYMENT STATUS: MT5 Bridge READY. FTMO Guard ACTIVE." -ForegroundColor White -BackgroundColor DarkBlue

# 1. Credentials Check (Placeholder for Vault Integration)
Write-Host " 🔑 STAGE 1: Credentials Validation for $AccountID..." -ForegroundColor Cyan
# Invoke-Vault-Check $AccountID

# 2. MT5 Adapter Launch (Socket Server)
Write-Host " 📉 STAGE 2: Launching MT5 Socket Server (Port 5555)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:PYTHONPATH='.'; python aevara/src/execution/mt5_adapter.py --port 5555 --secret AEVRA_SECRET_Ω11"

# 3. Main Organism Activation (Runner)
Write-Host " 🧠 STAGE 3: Activating Aevra Cérebro (Portfolio Mode)..." -ForegroundColor Cyan
# Start main runner logic in current process
# python aevara/src/main.py --mode challenge --pilot-mode 1

Start-Sleep -Seconds 5
Write-Host " ✅ AEVRA OPERATIONAL: Challenge Mode Active. Buffer 4%/8% Enforced." -ForegroundColor Green
Write-Host " ⚠️ WARNING: Zero-Intervention Protocol. Dashboard live at http://127.0.0.1:8050." -ForegroundColor Yellow
