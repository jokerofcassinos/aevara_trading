# @module: aevara.scripts.run_live_gateway
# @deps: aevara.src.execution.live_gateway
# @status: IMPLEMENTED
# @last_update: 2026-04-07
# @summary: PowerShell launcher for live gateway with mode, exchange, symbol, and max_dd_pct args.

param(
    [ValidateSet("dry-run", "shadow", "live")]
    [string]$Mode = "dry-run",

    [string]$Exchange = "binance",

    [string]$Symbol = "BTC/USDT",

    [float]$MaxDdPct = 4.8
)

Write-Host "================================================"
Write-Host "  AEVARA — LIVE EXECUTION GATEWAY LAUNCHER"
Write-Host "================================================"
Write-Host "  Mode       : $Mode"
Write-Host "  Exchange   : $Exchange"
Write-Host "  Symbol     : $Symbol"
Write-Host "  Max DD %   : $MaxDdPct"
Write-Host ""

# Validate environment
$envFile = Join-Path $PSScriptRoot "..\.env"
if (-not (Test-Path $envFile) -and $Mode -ne "dry-run") {
    Write-Host "[WARN] .env not found. Falling back to dry-run mode."
    $Mode = "dry-run"
}

Write-Host "[INIT] Loading modules..."

# Build Python launch command
$scriptRoot = Join-Path $PSScriptRoot ".."
$pythonCmd = "python"
$mainModule = "aevara.src.execution.live_gateway"

try {
    $process = Start-Process -FilePath $pythonCmd -ArgumentList "-m", $mainModule, "--mode", $Mode -NoNewWindow -PassThru -Wait
    if ($process.ExitCode -eq 0) {
        Write-Host "[OK] Gateway cycle completed successfully."
    } else {
        Write-Host "[ERROR] Gateway exited with code $($process.ExitCode)"
        exit $process.ExitCode
    }
} catch {
    Write-Host "[FATAL] Failed to launch gateway: $_"
    exit 1
}

Write-Host "[COMPLETE] Live gateway script finished."
