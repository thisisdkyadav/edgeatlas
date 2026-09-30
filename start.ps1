param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$edgeRoot = $PSScriptRoot
Set-Location -LiteralPath $edgeRoot
foreach ($edgePort in @(4100,4200,6333)) {
    if (Get-NetTCPConnection -LocalPort $edgePort -State Listen -ErrorAction SilentlyContinue) { throw "Port $edgePort is already in use. The demo may already be running." }
}
if (-not (Test-Path -LiteralPath 'tools/qdrant-server/qdrant.exe')) { throw 'Run setup.ps1 first, or start your own Qdrant Server and use separate terminals.' }
if (-not (Test-Path -LiteralPath 'dist/index.html')) { throw 'Build the frontend first with npm run build.' }
New-Item -ItemType Directory -Force -Path 'data/logs' | Out-Null
$env:QDRANT__SERVICE__HOST = '127.0.0.1'
$env:QDRANT__STORAGE__STORAGE_PATH = './data/qdrant'
$env:QDRANT__TELEMETRY_DISABLED = 'true'
$env:HF_HUB_OFFLINE = '1'
$edgePython = (Get-Command $Python).Source
$edgeProcesses = @()
$edgeServer = Start-Process -FilePath (Join-Path $edgeRoot 'tools/qdrant-server/qdrant.exe') -WorkingDirectory $edgeRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'data/logs/qdrant.stdout.log' -RedirectStandardError 'data/logs/qdrant.stderr.log'
$edgeProcesses += @{ id=$edgeServer.Id; start=$edgeServer.StartTime.ToUniversalTime().ToString('o'); name='qdrant' }
foreach ($edgeMode in @('cloud','edge')) {
    $edgeProcess = Start-Process -FilePath $edgePython -ArgumentList @(('"' + (Join-Path $edgeRoot 'run.py') + '"'),$edgeMode) -WorkingDirectory $edgeRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "data/logs/$edgeMode.stdout.log" -RedirectStandardError "data/logs/$edgeMode.stderr.log"
    $edgeProcesses += @{ id=$edgeProcess.Id; start=$edgeProcess.StartTime.ToUniversalTime().ToString('o'); name=$edgeMode }
}
$edgeProcesses | ConvertTo-Json | Set-Content -LiteralPath 'data/runtime.json'
Write-Host 'Starting local services. Open http://127.0.0.1:4100 after the model loads.'
Write-Host 'Logs: data/logs. Stop only these processes with .\stop.ps1.'
