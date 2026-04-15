#!/usr/bin/env pwsh
<#
Script de setup completo para Windows PowerShell
Bloco 1 + Bloco 2 (Persistência + Scheduler)

Uso:
    .\setup_windows.ps1
#>

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "SETUP COMPLETO: BLOCO 1 + BLOCO 2" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# Função para executar comando e verificar erro
function Invoke-Step {
    param(
        [string]$StepNumber,
        [string]$StepName,
        [scriptblock]$Command
    )

    Write-Host "[PASSO $StepNumber/4] $StepName" -ForegroundColor Yellow
    & $Command

    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Erro em: $StepName" -ForegroundColor Red
        Read-Host "Pressione Enter para sair"
        exit 1
    }
    Write-Host "✓ $StepName concluído" -ForegroundColor Green
    Write-Host ""
}

# Passo 1: Verificar/iniciar PostgreSQL
Invoke-Step "1" "Verificando PostgreSQL" {
    $running = docker-compose ps | Select-String "db.*Up"

    if ($running) {
        Write-Host "✓ PostgreSQL já está rodando" -ForegroundColor Green
    } else {
        Write-Host "⚠️  PostgreSQL não está rodando. Iniciando..." -ForegroundColor Yellow
        docker-compose up -d db
        Write-Host "⏳ Aguardando database ficar pronto (15s)..."
        Start-Sleep -Seconds 15
    }
}

# Passo 2: Migration
Invoke-Step "2" "Executando migration 004" {
    python executar_migration.py
}

# Passo 3: Popular dados (Bloco 1)
Invoke-Step "3" "Populando dados iniciais (Bloco 1)" {
    $env:OAB_SOMENTE_TJSP = "1"
    python scripts/testar_oab_361329.py
}

# Passo 4: Ativar monitoramento
Invoke-Step "4" "Ativando monitoramento para Bloco 2" {
    python scripts/ativar_monitoramento.py
}

# Finalização
Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "✓ SETUP CONCLUÍDO COM SUCESSO!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Próximo passo: Testar Scheduler Diário (Bloco 2)" -ForegroundColor Cyan
Write-Host ""
Write-Host "Opção 1: Teste manual (executa uma vez)" -ForegroundColor Yellow
Write-Host "  python scripts/testar_scheduler.py" -ForegroundColor White
Write-Host ""
Write-Host "Opção 2: Teste contínuo (FastAPI em background)" -ForegroundColor Yellow
Write-Host "  uvicorn main:app --reload" -ForegroundColor White
Write-Host ""
Write-Host "Opção 3: Agendar (APScheduler automático 24/7)" -ForegroundColor Yellow
Write-Host "  Aguarde até 2:00 AM (ou mude em .env)" -ForegroundColor White
Write-Host ""

Read-Host "Pressione Enter para sair"
