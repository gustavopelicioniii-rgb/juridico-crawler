import asyncio
import logging
import sys
import os

# Ajusta path para importar src
sys.path.append(os.getcwd())

# Mock settings se necessário (mas deve carregar do env)
from src.config import settings
from src.crawlers.datajud import DataJudCrawler
from src.crawlers.tjsp import TJSPCrawler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnostic")

async def diagnose():
    print("\n--- DIAGNÓSTICO JURIDICO CRAWLER (TESTE INTERNO) ---\n")
    print(f"DataJud: {settings.datajud_api_key[:10]}...")
    print(f"Firecrawl: {settings.firecrawl_api_key[:10]}...\n")
    
    oab_numero = "361329" # Exemplo comum em SP
    oab_uf = "SP"
    
    # 1. Testar DataJud
    print(">>> Testando DataJud (Busca Nacional)...")
    try:
        async with DataJudCrawler() as dj:
            # Busca em apenas 1 tribunal para ser rápido (TJSP)
            res = await dj.buscar_por_oab(oab_numero, oab_uf, tribunais=["tjsp"], usar_ai_parser=False, max_concorrentes=5)
            print(f"✓ DataJud TJSP: Encontrados {len(res)} processos.\n")
    except Exception as e:
        print(f"✗ Erro no DataJud: {e}\n")

    # 2. Testar TJSP eSaj (Direto/Firecrawl)
    print(">>> Testando TJSP eSaj (Portal Direto)...")
    try:
        async with TJSPCrawler() as tjsp:
            res = await tjsp.buscar_por_oab(oab_numero, oab_uf, paginas=1)
            print(f"✓ TJSP eSaj: Encontrados {len(res)} processos.\n")
    except Exception as e:
        print(f"✗ Erro no TJSP: {e}\n")

if __name__ == "__main__":
    asyncio.run(diagnose())
