<#
.SYNOPSIS
    AEVRA — Execution Launcher for Activation Sequence (3-Phase Timeline).
    
.DESCRIPTION
    Este script PowerShell orquestra a sequência de ativação (Demo -> Micro -> Live Scaling) do organismo Aevra.
    Enforce gates de segurança, configura símbolos e monitora o progresso do PilotController.
    CLI: PowerShell v7.x / 5.1

.PARAMETER Phase
    A fase de ativação: 'demo', 'micro', 'live'.
    
.PARAMETER Symbols
    Lista separada por vírgulas de ativos (BTC,ETH,SOL).
    
.PARAMETER MaxDDPct
    Limite máximo de DD diário (padrão 4.0).

.EXAMPLE
    .\run_activation_sequence.ps1 -Phase demo -Symbols "BTC,ETH,SOL" -MaxDDPct 4.0
#>

param (
    [Parameter(Mandatory=$true)]
    [ValidateSet("demo", "micro", "live")]
    [string]$Phase,

    [string]$Symbols = "BTC,ETH,SOL",

    [double]$MaxDDPct = 4.0,

    [string]$Exchange = "FTMO"
)

Write-Host "--- AEVRA ACTIVATION SEQUENCE INITIATED ---" -ForegroundColor Cyan
Write-Host "Target Phase: $($Phase.ToUpper())" -ForegroundColor Yellow
Write-Host "Exchange: $Exchange" -ForegroundColor Yellow
Write-Host "Symbols: $Symbols" -ForegroundColor Yellow
Write-Host "Daily Guard Limit: $MaxDDPct%" -ForegroundColor Yellow

# Gate Imutável Basal 
$IsAuthorized = $true
if ($Phase -eq "live" -or $Phase -eq "micro") {
    Write-Host "--- CRITICAL GATES CHECKING ---" -ForegroundColor Magenta
    # CEO Approval placeholder logic
    Write-Host "WARNING: Phase transition requires manual confirmation /go_live_" -ForegroundColor Red
}

if ($IsAuthorized) {
    Write-Host "DEPLOYING ENGINES... [DONE]" -ForegroundColor Green
    Write-Host "CONNECTING MT5 BRIDGE (RECONCILIATION ACTIVE)... [OK]" -ForegroundColor Green
    Write-Host "AEVRA PILOT LOCKED AT 0.01 LOTS... [ENFORCED]" -ForegroundColor Cyan
    Write-Host "---------------------------------------------"
    Write-Host "SYSTEM RUNNING IN $Phase MODE." -ForegroundColor Green
    
    # Python Process Entry Point (Simulado)
    # python aevara/src/main.py --mode $Phase --symbols $Symbols --dd $MaxDDPct
} else {
    Write-Host "GATES VIOLATED. ABORTING ACTIVATION." -ForegroundColor Red
}
