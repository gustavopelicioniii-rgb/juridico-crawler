# Script para rodar o Jurídico Crawler Sem Docker (Modo Lite)
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "INICIANDO JURIDICO CRAWLER (MODO SEM DOCKER)" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Garantir dependências
Write-Host "[*] Verificando dependências..." -ForegroundColor Yellow
pip install aiosqlite httpx -q

# 2. Configurar variáveis de ambiente para SQLite
$env:DATABASE_URL = "sqlite+aiosqlite:///juridico.db"
$env:PORT = "8080"
$env:API_DEBUG = "True"

Write-Host "[OK] Banco de dados definido como: juridico.db" -ForegroundColor Green
Write-Host "[OK] Porta definida como: 8080" -ForegroundColor Green

# 3. Iniciar a API
Write-Host "[*] Iniciando servidor Uvicorn..." -ForegroundColor Yellow
Write-Host "Acesse em: http://localhost:8080" -ForegroundColor Green
python main.py
