$ErrorActionPreference = 'Stop'
$edgeState = Join-Path $PSScriptRoot 'data/runtime.json'
if (-not (Test-Path -LiteralPath $edgeState)) { Write-Host 'No launcher state found.'; exit }
foreach ($edgeRecord in (Get-Content -LiteralPath $edgeState -Raw | ConvertFrom-Json)) {
    $edgeProcess = Get-Process -Id $edgeRecord.id -ErrorAction SilentlyContinue
    $edgeExpectedStart = ([datetime]$edgeRecord.start).ToUniversalTime()
    if ($edgeProcess -and $edgeProcess.StartTime.ToUniversalTime().Ticks -eq $edgeExpectedStart.Ticks) {
        Stop-Process -Id $edgeRecord.id
        Write-Host "Stopped $($edgeRecord.name)."
    }
}
