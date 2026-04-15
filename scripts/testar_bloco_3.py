#!/usr/bin/env python
"""
Script de teste: Bloco 3 — Motor de Prazos

Demonstra:
1. Detecção automática de prazos a partir de movimentações
2. Cálculo de datas de vencimento (dias úteis)
3. Notificações automáticas de prazos vencendo
4. Marcação de prazos cumpridos

Uso:
    python scripts/testar_bloco_3.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


async def teste_bloco_3():
    """Executa testes do Bloco 3."""
    try:
        from src.database.connection import AsyncSessionLocal
        from src.database.models import Processo, Movimentacao, Prazo
        from src.services.prazo_service import PrazoService
        from sqlalchemy import select

        print("")
        print("=" * 70)
        print("TESTE: BLOCO 3 — MOTOR DE PRAZOS")
        print("=" * 70)
        print("")

        async with AsyncSessionLocal() as db:
            # 1. Busca processos existentes
            result = await db.execute(select(Processo).limit(1))
            processo = result.scalar_one_or_none()

            if not processo:
                print("✗ Nenhum processo encontrado no banco!")
                print("Execute primeiro: python scripts/testar_oab_361329.py")
                return False

            print(f"[1] Processo selecionado: {processo.numero_cnj}")
            print("")

            # 2. Busca movimentações do processo
            result = await db.execute(
                select(Movimentacao).where(
                    Movimentacao.processo_id == processo.id
                ).limit(10)
            )
            movimentacoes = result.scalars().all()

            print(f"[2] Analisando {len(movimentacoes)} movimentações...")
            print("")

            # 3. Testa PrazoService
            prazo_service = PrazoService(db)

            prazos_criados_total = 0
            for mov in movimentacoes:
                prazos = await prazo_service.detectar_prazos_por_movimentacao(mov)

                if prazos:
                    for prazo in prazos:
                        prazos_criados_total += 1
                        dias_ate_vencimento = (
                            prazo.data_vencimento - datetime.now().date()
                        ).days
                        print(
                            f"   ✓ Prazo detectado:"
                        )
                        print(
                            f"     Tipo: {prazo.tipo_prazo}"
                        )
                        print(
                            f"     Descrição: {prazo.descricao}"
                        )
                        print(
                            f"     Iniciado em: {prazo.data_inicio}"
                        )
                        print(
                            f"     Vence em: {prazo.data_vencimento} "
                            f"({dias_ate_vencimento} dias)"
                        )
                        print("")

            await db.commit()

            if prazos_criados_total == 0:
                print("   ℹ️  Nenhum prazo detectado nas movimentações")
                print("   Exemplo de movimentações que criam prazos:")
                print("   - 'Citação' → Prazo CONTESTACAO")
                print("   - 'Sentença' → Prazo RECURSO")
                print("   - 'Apelação' → Prazo CONTRARRAZAO")
                print("")

            # 4. Obtém prazos criados
            result = await db.execute(
                select(Prazo).where(Prazo.processo_id == processo.id)
            )
            todos_prazos = result.scalars().all()

            print(f"[3] Status dos Prazos:")
            status = prazo_service.resumo_status_prazos(todos_prazos)
            print(f"   Total de prazos: {status['total']}")
            print(f"   Abertos: {status['abertos']}")
            print(f"   Cumpridos: {status['cumpridos']}")
            print(f"   Vencidos: {status['vencidos']}")
            print(f"   Vencendo em 3 dias: {status['vencendo_em_3_dias']}")
            print("")

            # 5. Busca prazos vencendo
            prazos_vencendo = await prazo_service.obter_prazos_vencendo(
                dias_antecedencia=3
            )

            if prazos_vencendo:
                print(f"[4] Prazos Vencendo (próximos 3 dias):")
                for prazo in prazos_vencendo:
                    dias_faltam = (
                        prazo.data_vencimento - datetime.now().date()
                    ).days
                    print(
                        f"   ⚠️  {prazo.tipo_prazo}: vence em {dias_faltam} dias"
                    )
            else:
                print(f"[4] Prazos Vencendo: nenhum nos próximos 3 dias")

            print("")

            print("=" * 70)
            print("✓ TESTE CONCLUÍDO")
            print("=" * 70)
            print("")

            # Sumário
            print("RESUMO:")
            print(f"  • Prazos criados: {prazos_criados_total}")
            print(f"  • Total no banco: {status['total']}")
            print(f"  • Abertos: {status['abertos']}")
            print(f"  • Vencendo em 3 dias: {status['vencendo_em_3_dias']}")
            print("")
            print("PRÓXIMOS PASSOS:")
            print("  1. Execute scheduler: python scripts/testar_scheduler.py")
            print("  2. Novos prazos serão detectados automaticamente")
            print("  3. Notificações serão criadas 3 dias antes do vencimento")
            print("")

            return True

    except Exception as e:
        print(f"\n✗ ERRO: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        sucesso = asyncio.run(teste_bloco_3())
        sys.exit(0 if sucesso else 1)
    except Exception as e:
        print(f"\n✗ ERRO FATAL: {str(e)}", file=sys.stderr)
        sys.exit(1)
