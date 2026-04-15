#!/usr/bin/env pwsh
<#
Script para iniciar a API REST
#>

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Iniciando API REST" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Verificar se está no diretório correto
if (!(Test-Path "main.py")) {
    Write-Host "Erro: main.py não encontrado!" -ForegroundColor Red
    Write-Host "Certifique-se de estar em: juridico-crawler/" -ForegroundColor Yellow
    exit 1
}

# Instalar dependências
Write-Host "Instalando dependências..." -ForegroundColor Yellow
pip install fastapi uvicorn sqlalchemy asyncpg -U

# Iniciar servidor
Write-Host ""
Write-Host "Iniciando servidor..." -ForegroundColor Green
Write-Host ""
Write-Host "Dashboard: http://localhost:8000" -ForegroundColor Cyan
Write-Host "Documentação: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "ReDoc: http://localhost:8000/redoc" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pressione Ctrl+C para parar" -ForegroundColor Yellow
Write-Host ""

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
