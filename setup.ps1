param([string]$Python = 'python', [switch]$SkipQdrant)
$ErrorActionPreference = 'Stop'
$edgeRoot = $PSScriptRoot
Set-Location -LiteralPath $edgeRoot
& $Python -m pip install --target .pydeps -r requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
if (-not $SkipQdrant -and -not (Test-Path -LiteralPath 'tools/qdrant-server/qdrant.exe')) {
    New-Item -ItemType Directory -Force -Path tools | Out-Null
    Invoke-WebRequest -Uri 'https://github.com/qdrant/qdrant/releases/download/v1.19.1/qdrant-x86_64-pc-windows-msvc.zip' -OutFile 'tools/qdrant.zip'
    Expand-Archive -LiteralPath 'tools/qdrant.zip' -DestinationPath 'tools/qdrant-server' -Force
}
& $Python run.py warm-model
if ($LASTEXITCODE -ne 0) { throw 'The local embedding model could not be prepared.' }
& npm.cmd ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
& npm.cmd run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
Write-Host 'Ready. Run .\start.ps1, then open http://127.0.0.1:4100.'
