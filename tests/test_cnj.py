import asyncio
import sys
import os

sys.path.append(os.getcwd())

from src.crawlers.tjsp import TJSPCrawler

async def main():
    async with TJSPCrawler() as c:
        p = await c.buscar_processo('1003032-46.2023.8.26.0048')
        print(f"Vara: {p.vara}")
        print(f"Comarca: {p.comarca}")
        print(f"Valor: {p.valor_causa}")
        print(f"Partes:")
        for pt in p.partes:
            print(f"  {pt.tipo_parte}: {pt.nome}")

asyncio.run(main())
