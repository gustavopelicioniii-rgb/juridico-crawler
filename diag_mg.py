
import asyncio
from src.crawlers.tjmg import TJMG_UnifiedCrawler
from src.crawlers.pje import PJeCrawler
from src.crawlers.eproc import EProcCrawler

async def diagnostico_mg():
    oab = "202030"
    uf = "MG"
    nome = "PELICIONI"
    
    print(f"\n--- INICIANDO DIAGNÓSTICO PROFUNDO MG (OAB {oab}/{uf}) ---")
    
    # 1. Testar TJMG
    print("\n🔍 Testando TJMG (PJe + Portal)...")
    try:
        async with TJMG_UnifiedCrawler() as c:
            r = await c.buscar_por_oab(oab, uf)
            print(f"✅ TJMG retornou {len(r)} processos.")
            for p in r:
                print(f"   - {p.numero_cnj} ({p.tribunal})")
    except Exception as e:
        print(f"❌ Erro no TJMG: {e}")

    # 2. Testar TRT3 (PJe Trabalho MG)
    print("\n🔍 Testando TRT3 (Justiça do Trabalho)...")
    try:
        async with PJeCrawler() as c:
            r = await c.buscar_por_oab(oab, uf, tribunais=["trt3"])
            print(f"✅ TRT3 retornou {len(r)} processos.")
            for p in r:
                print(f"   - {p.numero_cnj} ({p.tribunal})")
    except Exception as e:
        print(f"❌ Erro no TRT3: {e}")

    # 3. Testar TRF6 (Justiça Federal MG)
    print("\n🔍 Testando TRF6 (Justiça Federal)...")
    try:
        # TRF6 costuma usar PJe ou eProc dependendo da fase
        async with PJeCrawler() as c:
            r = await c.buscar_por_oab(oab, uf, tribunais=["trf6"])
            print(f"✅ TRF6 (PJe) retornou {len(r)} processos.")
            for p in r:
                print(f"   - {p.numero_cnj} ({p.tribunal})")
    except Exception as e:
        print(f"❌ Erro no TRF6: {e}")

if __name__ == "__main__":
    asyncio.run(diagnostico_mg())
