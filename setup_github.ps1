# ============================================================
# setup_github.ps1 - Publica o projeto juridico-crawler no GitHub
# Basta dar dois cliques ou rodar no PowerShell
# ============================================================

$GITHUB_USER = "gustavopelicioniii-rgb"
$REPO_NAME   = "juridico-crawler"
$BRANCH      = "main"

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "  Publicando $REPO_NAME no GitHub..." -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Verifica se git esta instalado
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[ERRO] Git nao encontrado. Baixe em https://git-scm.com/download/win" -ForegroundColor Red
    Read-Host "Pressione Enter para sair"
    exit 1
}

# Vai para a pasta do script
Set-Location $PSScriptRoot

# Inicializa o repositorio
Write-Host "[1/5] Inicializando repositorio Git..." -ForegroundColor Yellow
git init -b $BRANCH

# Configura usuario se ainda nao estiver configurado
$gitName = git config user.name 2>$null
if (-not $gitName) {
    $userName = Read-Host "Digite seu nome para o Git (ex: Gustavo)"
    $userEmail = Read-Host "Digite seu email do GitHub"
    git config user.name "$userName"
    git config user.email "$userEmail"
}

# Adiciona todos os arquivos
Write-Host ""
Write-Host "[2/5] Adicionando arquivos..." -ForegroundColor Yellow
git add .

# Primeiro commit
Write-Host ""
Write-Host "[3/5] Criando primeiro commit..." -ForegroundColor Yellow
git commit -m "chore: primeiro commit - juridico-crawler"

# Verifica se gh CLI esta instalado
Write-Host ""
Write-Host "[4/5] Criando repositorio no GitHub..." -ForegroundColor Yellow

if (Get-Command gh -ErrorAction SilentlyContinue) {
    # Usa GitHub CLI (automatico)
    Write-Host "GitHub CLI encontrado. Criando repositorio automaticamente..." -ForegroundColor Green
    gh repo create "$GITHUB_USER/$REPO_NAME" --public --source=. --remote=origin --push
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "======================================" -ForegroundColor Green
        Write-Host "  Sucesso! Repositorio publicado em:" -ForegroundColor Green
        Write-Host "  https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
        Write-Host "======================================" -ForegroundColor Green
    } else {
        Write-Host "[AVISO] Falha ao criar via CLI. Tente o passo manual abaixo." -ForegroundColor Yellow
    }
} else {
    # Instrucoes manuais se gh CLI nao estiver instalado
    Write-Host ""
    Write-Host "GitHub CLI nao encontrado. Siga os passos:" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "1. Acesse: https://github.com/new" -ForegroundColor White
    Write-Host "2. Nome do repositorio: $REPO_NAME" -ForegroundColor White
    Write-Host "3. Deixe em branco (sem README, sem .gitignore)" -ForegroundColor White
    Write-Host "4. Clique em 'Create repository'" -ForegroundColor White
    Write-Host ""
    Read-Host "Depois de criar o repositorio, pressione Enter para continuar"

    Write-Host ""
    Write-Host "[5/5] Conectando e enviando para o GitHub..." -ForegroundColor Yellow
    git remote add origin "https://github.com/$GITHUB_USER/$REPO_NAME.git"
    git push -u origin $BRANCH

    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "======================================" -ForegroundColor Green
        Write-Host "  Sucesso! Repositorio publicado em:" -ForegroundColor Green
        Write-Host "  https://github.com/$GITHUB_USER/$REPO_NAME" -ForegroundColor Green
        Write-Host "======================================" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "[ERRO] Falha no push. Verifique suas credenciais do GitHub." -ForegroundColor Red
        Write-Host "Dica: configure um token em https://github.com/settings/tokens" -ForegroundColor Yellow
    }
}

Write-Host ""
Read-Host "Pressione Enter para fechar"
