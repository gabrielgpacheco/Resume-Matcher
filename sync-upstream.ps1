# sync-upstream.ps1
# Sincroniza o fork com o repositorio original (srbhr/Resume-Matcher),
# preservando suas melhorias locais.
#
# Faz: git fetch upstream + merge de upstream/main na branch atual.
# Se houver conflito, o merge para e o git indica os arquivos para resolver.
#
# Uso:  powershell -ExecutionPolicy Bypass -File .\sync-upstream.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "== Buscando novidades do upstream ==" -ForegroundColor Cyan
git fetch upstream

$current = git branch --show-current
if ($current -ne "main") {
    Write-Warning "Voce esta na branch '$current'. Sincronize a 'main' primeiro:"
    Write-Warning "  git switch main"
    Write-Warning "  .\sync-upstream.ps1"
    Write-Warning "  git rebase main (na sua branch de feature)"
    exit 0
}

Write-Host "== Fazendo merge de upstream/main em main ==" -ForegroundColor Cyan
git merge upstream/main

if ($LASTEXITCODE -eq 0) {
    Write-Host "Sincronizado com sucesso." -ForegroundColor Green
    Write-Host "Se quiser publicar no seu fork: git push origin main"
} else {
    Write-Host "Merge com conflito. Resolva os conflitos, depois: git add . ; git commit" -ForegroundColor Yellow
}
