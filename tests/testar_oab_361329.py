"""
Script para trazer os 39 processos da OAB 361329 para o banco local
"""
import asyncio
import os
from src.crawlers.datajud import DataJudCrawler
from src.database.connection import AsyncSessionLocal
from src.services.processo_service import ProcessoService

async def main():
    print("\n" + "="*70)
    print("🔄 IMPORTANDO PROCESSOS DA OAB 361329 SP")
    print("="*70 + "\n")

    # Configurar para pegar apenas TJSP
    os.environ['OAB_SOMENTE_TJSP'] = '1'
    os.environ['OAB_NUMERO'] = '361329'
    os.environ['OAB_UF'] = 'SP'

    try:
        crawler = DataJudCrawler()
        async with AsyncSessionLocal() as session:
            service = ProcessoService()

            print("📥 Buscando processos no DataJud...")

            # Buscar processos
            processos_novos = await crawler.buscar_processos_oab(
                numero_oab="361329",
                uf="SP"
            )

            print(f"✓ Encontrados {len(processos_novos)} processos")

            # Salvar no banco
            if processos_novos:
                print("\n💾 Salvando processos no banco...")
                stats = await service.processar_processos_datajud(
                    session=session,
                    processos=processos_novos,
                    tenant_id=1
                )

                print(f"\n✓ Processamento concluído:")
                print(f"  • Processos processados: {stats['total_processados']}")
                print(f"  • Novos: {stats['novos']}")
                print(f"  • Atualizados: {stats['atualizados']}")
                print(f"  • Movimentações novas: {stats['movimentacoes_novas']}")

                await session.commit()
                print("\n✅ Dados salvos com sucesso!")
            else:
                print("⚠️  Nenhum processo encontrado")

    except Exception as e:
        print(f"\n✗ Erro: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
