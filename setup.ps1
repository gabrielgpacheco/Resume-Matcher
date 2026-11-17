# setup.ps1
# Configuracao idempotente do Resume-Matcher (fork local) em uma maquina nova.
#
# Faz, sem repetir o que ja existe:
#   1. Cria o fork gabrielgpacheco/Resume-Matcher (via gh CLI)
#   2. Clona em um diretorio temporario e move o conteudo para a pasta atual
#   3. Configura o remote upstream
#   4. Cria o .env a partir do .env.example (se nao existir)
#   5. uv sync (backend) e npm install (frontend)
#
# Pre-requisitos: git, gh CLI logado, Python >= 3.14, uv, Node >= 20.
# Uso:  powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$FORK = "gabrielgpacheco/Resume-Matcher"
$UPSTREAM = "srbhr/Resume-Matcher"

function Write-Step([string]$msg) {
    Write-Host "`n== $msg ==" -ForegroundColor Cyan
}

# 1. Fork (uma vez)
Write-Step "Criando o fork (se ainda nao existir)"
$forkExists = gh repo view $FORK --json name 2>$null
if (-not $forkExists) {
    gh repo fork $UPSTREAM --clone=false
} else {
    Write-Host "Fork $FORK ja existe. Pulando."
}

# 2. Clone preservando arquivos locais (este script, GUIA-PROJETO.md, etc.)
$alreadyCloned = Test-Path (Join-Path $root ".git")
if (-not $alreadyCloned) {
    Write-Step "Clonando o fork"
    $tmp = Join-Path $env:TEMP "resume-matcher-clone"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    git clone "https://github.com/$FORK.git" $tmp
    Get-ChildItem -Force $tmp | Move-Item -Destination $root -Force
    Remove-Item $tmp -Recurse -Force
} else {
    Write-Host "Repositorio ja clonado. Pulando."
}

# 3. Remote upstream
Write-Step "Configurando remote upstream"
$hasUpstream = git remote | Select-String -Quiet "^upstream$"
if (-not $hasUpstream) {
    git remote add upstream "https://github.com/$UPSTREAM.git"
}
git fetch upstream

# 4. .env
Write-Step "Criando .env (se nao existir)"
$envPath = Join-Path $root "apps\backend\.env"
$envExample = Join-Path $root "apps\backend\.env.example"
if (-not (Test-Path $envPath)) {
    Copy-Item $envExample $envPath
    Write-Host ".env criado a partir do .env.example. Configure LLM_PROVIDER/LLM_MODEL/LLM_API_KEY."
} else {
    Write-Host ".env ja existe. Pulando."
}

# 5. Dependencias
Write-Step "Instalando dependencias do backend (uv sync)"
Set-Location (Join-Path $root "apps\backend")
uv sync

Write-Step "Instalando dependencias do frontend (npm install)"
Set-Location (Join-Path $root "apps\frontend")
npm install

Set-Location $root
Write-Host "`nSetup concluido. Para rodar: .\start.ps1" -ForegroundColor Green
