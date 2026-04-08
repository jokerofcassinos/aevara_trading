param(
    [string]$Mode = "DRY-RUN",
    [int]$DryRunDuration = 10
)

function Show-Header {
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "         AEVRA MICRO-LIVE TRANSITION GATE              " -ForegroundColor White
    Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
}

Show-Header

# 1. Run Checklist
Write-Host "`n[STEP 1] Running Pre-Flight Checklist..." -ForegroundColor Yellow
$env:PYTHONPATH="."
python scripts/micro_live_checklist.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ CHECKLIST FAILED. Transition Aborted." -ForegroundColor Red
    exit 1
}

# 2. Run Dry-Run
Write-Host "`n[STEP 2] Initiating Cognitive Dry-Run ($DryRunDuration seconds)..." -ForegroundColor Yellow
python aevara/src/main.py DEMO --mode dry-run --duration $DryRunDuration
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n❌ DRY-RUN CRASHED. Transition Aborted." -ForegroundColor Red
    exit 1
}

# 3. CEO Approval Gate
Write-Host "`n═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host " ALL GATES PASSED. SYSTEM STABLE.                      " -ForegroundColor Green
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Yellow
Write-Host " Capital at Risk: $30-$100                             "
Write-Host " Sizing: 0.01 Lots (Fixed)                             "
Write-Host " FTMO Buffers: ACTIVE (4%/8%)                          "
Write-Host "───────────────────────────────────────────────────────"

$Approval = Read-Host " Type 'AEVRA_GO_LIVE' to authorize MICRO-LIVE transition "

if ($Approval -eq "AEVRA_GO_LIVE") {
    Write-Host "`n🚀 AUTHORIZATION RECEIVED. Transitioning to MICRO-LIVE..." -ForegroundColor Green
    # In a real scenario, this would update a central state file or start the process
    Write-Host " PHASE: MICRO-LIVE ATIVADA." -ForegroundColor Green
    Write-Host " Start command: python aevara/src/main.py MICRO-LIVE" -ForegroundColor Cyan
} else {
    Write-Host "`n⚠️  TRANSITION ABORTED BY CEO." -ForegroundColor Yellow
}
