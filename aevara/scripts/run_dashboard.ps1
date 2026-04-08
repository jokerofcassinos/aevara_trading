# @module: aevara.scripts.run_dashboard
# @deps: aevara.src.interfaces.ceo_dashboard
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: PowerShell launcher for CEO dashboard with host, port, and max_queue settings.

param(
    [string]$HostAddr = "127.0.0.1",

    [int]$Port = 8099,

    [int]$MaxQueue = 500
)

Write-Host "=============================================="
Write-Host "  AEVARA — CEO DASHBOARD FEED LAUNCHER"
Write-Host "=============================================="
Write-Host "  Host         : $HostAddr"
Write-Host "  Port         : $Port"
Write-Host "  Max Queue    : $MaxQueue"
Write-Host ""

# Initialization
$scriptRoot = Join-Path $PSScriptRoot ".."
$pythonCmd = "python"
$mainModule = "aevara.src.interfaces.ceo_dashboard"

Write-Host "[INIT] Starting dashboard feed..."

try {
    # Call module
    $proc = Start-Process -FilePath $pythonCmd -ArgumentList "-m", $mainModule, "--host", $HostAddr, "--port", $Port -NoNewWindow -PassThru -Wait
    
    if ($proc.ExitCode -eq 0) {
        Write-Host "[OK] Dashboard feed finished normally."
    } else {
        Write-Host "[ERROR] Dashboard exited with code $($proc.ExitCode)"
        exit $proc.ExitCode
    }
} catch {
    Write-Host "[FATAL] Failed to launch dashboard: $_"
    exit 1
}

Write-Host "[COMPLETE] Dashboard script finished."
