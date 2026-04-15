#!/usr/bin/env pwsh
<#
Script para verificar dados no PostgreSQL
#>

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "VERIFICACAO DO BANCO DE DADOS" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$queries = @(
    @{name = "Total de Processos"; query = "SELECT COUNT(*) as total FROM processos;"},
    @{name = "Total de Movimentacoes"; query = "SELECT COUNT(*) as total FROM movimentacoes;"},
    @{name = "Monitoramentos Ativos"; query = "SELECT COUNT(*) as total FROM monitoramentos WHERE ativo=True;"},
    @{name = "Notificacoes Nao Lidas"; query = "SELECT COUNT(*) as total FROM notificacoes WHERE lida=False;"},
    @{name = "Ultima Execucao do Scheduler"; query = "SELECT MAX(ultima_verificacao) as ultima FROM monitoramentos;"}
)

foreach ($q in $queries) {
    Write-Host "[*] $($q.name)" -ForegroundColor Yellow
    psql -U postgres -d juridico_crawler -c $q.query
    Write-Host ""
}

Write-Host "======================================================================" -ForegroundColor Green
Write-Host "Verificacao concluida!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
