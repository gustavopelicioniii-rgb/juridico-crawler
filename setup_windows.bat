@echo off
REM Script de setup completo para Windows
REM Bloco 1 + Bloco 2 (Persistência + Scheduler)

setlocal enabledelayedexpansion

echo.
echo ======================================================================
echo SETUP COMPLETO: BLOCO 1 + BLOCO 2
echo ======================================================================
echo.

REM Passo 1: Verificar se PostgreSQL está rodando
echo [PASSO 1/4] Verificando PostgreSQL...
docker-compose ps | findstr db >nul
if %errorlevel% neq 0 (
    echo.
    echo ✗ PostgreSQL não está rodando!
    echo Iniciando PostgreSQL...
    docker-compose up -d db
    timeout /t 15
) else (
    echo ✓ PostgreSQL já está rodando
)

echo.
echo [PASSO 2/4] Executando migration...
python executar_migration.py
if %errorlevel% neq 0 (
    echo ✗ Erro na migration!
    pause
    exit /b 1
)
echo ✓ Migration concluída

echo.
echo [PASSO 3/4] Populando dados iniciais (Bloco 1)...
set OAB_SOMENTE_TJSP=1
python scripts/testar_oab_361329.py
if %errorlevel% neq 0 (
    echo ✗ Erro ao popular dados!
    pause
    exit /b 1
)
echo ✓ Dados carregados

echo.
echo [PASSO 4/4] Ativando monitoramento para Bloco 2...
python scripts/ativar_monitoramento.py
if %errorlevel% neq 0 (
    echo ✗ Erro ao ativar monitoramento!
    pause
    exit /b 1
)
echo ✓ Monitoramento ativado

echo.
echo ======================================================================
echo ✓ SETUP CONCLUÍDO COM SUCESSO!
echo ======================================================================
echo.
echo Próximo passo: Testar Scheduler
echo.
echo Opção 1: Teste manual (uma execução)
echo   python scripts/testar_scheduler.py
echo.
echo Opção 2: Teste contínuo (FastAPI em background)
echo   uvicorn main:app
echo.
pause
