import asyncio
import os
import sys

# Add /app to sys.path
sys.path.append("/app")

from src.crawlers.datajud import DataJudCrawler
from src.config import settings

async def test():
    print(f"Testing OAB 361329 SP with API Key: {settings.datajud_api_key[:10]}...")
    async with DataJudCrawler() as dj:
        try:
            results = await dj.buscar_por_oab("361329", "SP", tribunais=["tjsp"])
            print(f"RESULTS FOUND: {len(results)}")
            for p in results[:5]:
                print(f"- {p.numero_cnj} ({len(p.partes)} partes)")
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test())
