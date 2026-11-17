# start.ps1
# Sobe o backend e o frontend do Resume-Matcher em janelas separadas,
# aguarda as portas e abre o navegador.
#
# Uso:  powershell -ExecutionPolicy Bypass -File .\start.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

$backendDir = Join-Path $root "apps\backend"
$frontendDir = Join-Path $root "apps\frontend"

function Test-Port([int]$port) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

Write-Host "== Iniciando backend (http://127.0.0.1:8000) ==" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$backendDir'; uv run app" -WorkingDirectory $backendDir

Write-Host "== Iniciando frontend (http://localhost:3000) ==" -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$frontendDir'; npm run dev" -WorkingDirectory $frontendDir

# Aguarda as portas ficarem disponíveis (até 90s cada)
foreach ($port in 8000, 3000) {
    $tries = 0
    while (-not (Test-Port $port) -and $tries -lt 90) {
        Start-Sleep -Seconds 1
        $tries++
    }
    if (Test-Port $port) {
        Write-Host "Porta ${port} no ar." -ForegroundColor Green
    } else {
        Write-Warning "Porta ${port} nao respondeu apos 90s. Verifique a janela correspondente."
    }
}

Start-Process "http://localhost:3000"
Write-Host "Pronto. Acesse http://localhost:3000" -ForegroundColor Green
