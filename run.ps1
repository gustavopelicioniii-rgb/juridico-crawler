#!/usr/bin/env pwsh
<#
Script helper para executar comandos Python corretamente no Windows

Uso:
    .\run.ps1 ativar-monitoramento
    .\run.ps1 testar-scheduler
    .\run.ps1 testar-oab
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("ativar-monitoramento", "testar-scheduler", "testar-oab", "verificar-banco", "testar-bloco-3")]
    [string]$Comando
)

# Garantir que está no diretório correto
$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $rootDir

Write-Host ""
Write-Host "Diretorio: $(Get-Location)" -ForegroundColor Cyan
Write-Host ""

switch ($Comando) {
    "ativar-monitoramento" {
        Write-Host "Ativando monitoramento..." -ForegroundColor Yellow
        python scripts/ativar_monitoramento.py
    }

    "testar-scheduler" {
        Write-Host "Testando scheduler..." -ForegroundColor Yellow
        python scripts/testar_scheduler.py
    }

    "testar-oab" {
        Write-Host "Testando OAB 361329..." -ForegroundColor Yellow
        $env:OAB_SOMENTE_TJSP = 1
        python scripts/testar_oab_361329.py
    }

    "verificar-banco" {
        Write-Host "Verificando banco de dados..." -ForegroundColor Yellow
        python scripts/verificar_banco.py
    }

    "testar-bloco-3" {
        Write-Host "Testando Bloco 3 - Motor de Prazos..." -ForegroundColor Yellow
        python scripts/testar_bloco_3.py
    }
}

Write-Host ""
