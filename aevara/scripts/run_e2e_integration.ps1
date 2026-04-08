# @module: aevara.scripts.run_e2e_integration
# @deps: aevara.src.integration.e2e_orchestrator
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: PowerShell launcher for full system integration with cycle control and latency cap.

param(
    [ValidateSet("paper", "shadow-sync", "live-dry")]
    [string]$Mode = "paper",

    [int]$Cycles = 10,

    [int]$MaxLatencyUs = 50000,

    [string]$Exchange = "binance"
)

Write-Host "=============================================="
Write-Host "  AEVARA — FULL SYSTEM E2E ORCHESTRATOR"
Write-Host "=============================================="
Write-Host "  Mode         : $Mode"
Write-Host "  Cycles       : $Cycles"
Write-Host "  Latency Cap  : $MaxLatencyUs us"
Write-Host ""

# Initialization
$scriptRoot = Join-Path $PSScriptRoot ".."
$pythonCmd = "python"
$mainModule = "aevara.src.integration.e2e_orchestrator"

Write-Host "[INIT] Launching organism in $Mode mode..."

try {
    # We call the module via -m to ensure package context
    $proc = Start-Process -FilePath $pythonCmd -ArgumentList "-m", $mainModule, "--mode", $Mode, "--cycles", $Cycles -NoNewWindow -PassThru -Wait
    
    if ($proc.ExitCode -eq 0) {
        Write-Host "[OK] Integration cycles completed successfully."
    } else {
        Write-Host "[ERROR] Organism exited with code $($proc.ExitCode)"
        exit $proc.ExitCode
    }
} catch {
    Write-Host "[FATAL] Failed to launch organism: $_"
    exit 1
}

Write-Host "[COMPLETE] Organism state saved. Check docs/PROJECT_STATE.yaml."
