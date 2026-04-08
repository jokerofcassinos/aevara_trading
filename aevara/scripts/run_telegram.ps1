# @module: aevara.scripts.run_telegram
# @deps: aevara.src.interfaces.telegram_bridge
# @status: IMPLEMENTED
# @last_update: 2026-04-10
# @summary: PowerShell launcher for Telegram bridge with token, mode, and allowed_chats settings.

param(
    [string]$Token = "ENV_TELEGRAM_TOKEN",

    [int[]]$AllowedChats = @(),

    [string]$Mode = "paper"
)

Write-Host "=============================================="
Write-Host "  AEVARA — TELEGRAM BRIDGE LAUNCHER"
Write-Host "=============================================="
Write-Host "  Mode         : $Mode"
Write-Host "  Tokens       : [MASKED]"
Write-Host "  Allowed Chats: $($AllowedChats -join ', ')"
Write-Host ""

# Initialization
$scriptRoot = Join-Path $PSScriptRoot ".."
$pythonCmd = "python"
$mainModule = "aevara.src.interfaces.telegram_bridge"

Write-Host "[INIT] Launching Telegram orchestrator..."

try {
    # Call module
    $proc = Start-Process -FilePath $pythonCmd -ArgumentList "-m", $mainModule, "--mode", $Mode -NoNewWindow -PassThru -Wait
    
    if ($proc.ExitCode -eq 0) {
        Write-Host "[OK] Telegram bridge finished normally."
    } else {
        Write-Host "[ERROR] Bridge exited with code $($proc.ExitCode)"
        exit $proc.ExitCode
    }
} catch {
    Write-Host "[FATAL] Failed to launch bridge: $_"
    exit 1
}

Write-Host "[COMPLETE] Telegram script finished."
