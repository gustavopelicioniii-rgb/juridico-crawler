#!/usr/bin/env python
"""
Script para ativar monitoramento de processos para Bloco 2 (Scheduler)

Uso:
    python scripts/ativar_monitoramento.py

Resultado:
    ✓ Ativa monitoramento para todos os 39 processos
    ✓ Define email de notificação
    ✓ Próxima verificação: agora (scheduler verificará imediatamente)
"""
import asyncio
import sys
import os
from datetime import datetime
from pathlib import Path

# Adiciona o diretório raiz do projeto ao path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def ativar_monitoramento_todos():
    """Ativa monitoramento para todos os processos."""
    try:
        from src.database.connection import AsyncSessionLocal
        from src.database.models import Processo, Monitoramento
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            # Busca todos os processos
            result = await db.execute(select(Processo))
            processos = result.scalars().all()

            print("=" * 70)
            print("ATIVANDO MONITORAMENTO PARA PROCESSOS")
            print("=" * 70)
            print(f"Total de processos encontrados: {len(processos)}\n")

            if not processos:
                print("✗ Nenhum processo encontrado no banco!")
                return False

            # Para cada processo, cria monitoramento se não existir
            criados = 0
            ja_existentes = 0

            for p in processos:
                # Verifica se já tem monitoramento
                result = await db.execute(
                    select(Monitoramento).where(
                        Monitoramento.processo_id == p.id
                    )
                )
                mon = result.scalar_one_or_none()

                if mon:
                    # Atualiza para ativo
                    if not mon.ativo:
                        mon.ativo = True
                        criados += 1
                    else:
                        ja_existentes += 1
                else:
                    # Cria novo monitoramento
                    mon = Monitoramento(
                        processo_id=p.id,
                        ativo=True,
                        notificar_email="escritorio@example.com",
                        proxima_verificacao=datetime.now(),
                    )
                    db.add(mon)
                    criados += 1

            await db.commit()

            print("=" * 70)
            print("RESULTADO")
            print("=" * 70)
            print(f"✓ Monitoramentos criados:     {criados}")
            print(f"✓ Já existentes:              {ja_existentes}")
            print(f"✓ Total ativo:                {criados + ja_existentes}")
            print()
            print("📌 Próximas ações:")
            print("   1. Aguarde até 2:00 AM (horário padrão do scheduler)")
            print("   2. OU execute manualmente:")
            print("      python scripts/testar_scheduler.py")
            print()
            print("=" * 70)

            return True

    except Exception as e:
        print(f"\n✗ ERRO: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        sucesso = asyncio.run(ativar_monitoramento_todos())
        sys.exit(0 if sucesso else 1)
    except Exception as e:
        print(f"\n✗ ERRO FATAL: {str(e)}", file=sys.stderr)
        sys.exit(1)
