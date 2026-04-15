#!/usr/bin/env python
"""
Script para verificar dados no PostgreSQL

Uso:
    python scripts/verificar_banco.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Adiciona src ao path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def verificar_banco():
    """Executa verificações no banco de dados."""
    try:
        from src.database.connection import AsyncSessionLocal
        from src.database.models import (
            Processo, Movimentacao, Monitoramento, Notificacao
        )
        from sqlalchemy import select, func

        async with AsyncSessionLocal() as db:
            print("")
            print("=" * 70)
            print("VERIFICACAO DO BANCO DE DADOS")
            print("=" * 70)
            print("")

            # 1. Total de processos
            result = await db.execute(select(func.count(Processo.id)))
            total_processos = result.scalar()
            print(f"[1] Total de Processos:        {total_processos}")

            # 2. Total de movimentações
            result = await db.execute(select(func.count(Movimentacao.id)))
            total_movimentacoes = result.scalar()
            print(f"[2] Total de Movimentacoes:    {total_movimentacoes}")

            # 3. Monitoramentos ativos
            result = await db.execute(
                select(func.count(Monitoramento.id)).where(
                    Monitoramento.ativo == True
                )
            )
            total_monitoramentos = result.scalar()
            print(f"[3] Monitoramentos Ativos:     {total_monitoramentos}")

            # 4. Notificações não lidas
            result = await db.execute(
                select(func.count(Notificacao.id)).where(
                    Notificacao.lida == False
                )
            )
            total_notificacoes = result.scalar()
            print(f"[4] Notificacoes Nao Lidas:    {total_notificacoes}")

            # 5. Última execução do scheduler
            result = await db.execute(
                select(func.max(Monitoramento.ultima_verificacao))
            )
            ultima_verificacao = result.scalar()
            print(f"[5] Ultima Verificacao:        {ultima_verificacao}")

            # 6. Próxima verificação agendada
            result = await db.execute(
                select(func.min(Monitoramento.proxima_verificacao))
            )
            proxima_verificacao = result.scalar()
            print(f"[6] Proxima Verificacao:       {proxima_verificacao}")

            # 7. Última movimentação registrada
            result = await db.execute(
                select(func.max(Movimentacao.data_movimentacao))
            )
            ultima_movimentacao = result.scalar()
            print(f"[7] Ultima Movimentacao:       {ultima_movimentacao}")

            print("")
            print("=" * 70)
            print("STATUS DO SISTEMA")
            print("=" * 70)

            # Status checks
            checks = [
                ("Processos cadastrados", total_processos > 0, total_processos),
                ("Movimentacoes registradas", total_movimentacoes > 0, total_movimentacoes),
                (
                    "Monitoramentos ativos",
                    total_monitoramentos > 0,
                    total_monitoramentos,
                ),
                (
                    "Scheduler executado",
                    ultima_verificacao is not None,
                    ultima_verificacao,
                ),
                (
                    "Proxima execucao agendada",
                    proxima_verificacao is not None,
                    proxima_verificacao,
                ),
            ]

            for check_name, passed, value in checks:
                status = "✓" if passed else "✗"
                print(f"{status} {check_name}: {value}")

            print("")
            print("=" * 70)

            if total_processos > 0 and total_monitoramentos > 0:
                print("✓ TUDO PRONTO! Bloco 1 + Bloco 2 funcionando!")
            else:
                print("⚠️  Algum dados faltando. Execute os passos anteriores.")

            print("=" * 70)
            print("")

            return True

    except Exception as e:
        print(f"\n✗ ERRO: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        sucesso = asyncio.run(verificar_banco())
        sys.exit(0 if sucesso else 1)
    except Exception as e:
        print(f"\n✗ ERRO FATAL: {str(e)}", file=sys.stderr)
        sys.exit(1)
