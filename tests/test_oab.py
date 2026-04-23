import asyncio
import logging
import sys
import os
sys.path.append(os.getcwd())

from src.crawlers.tjsp import TJSPCrawler

async def test_oab_extraction():
    cnj = '1003032-46.2023.8.26.0048'
    print(f"Testando extracao de OAB para o processo {cnj}...")
    
    async with TJSPCrawler() as crawler:
        processo = await crawler.buscar_processo(cnj)
        if not processo:
            print("Processo nao encontrado!")
            return
            
        print(f"CNJ: {processo.numero_cnj}")
        print(f"Situacao: {processo.situacao}")
        print("Partes encontradas:")
        for pt in processo.partes:
            print(f"  - {pt.nome} (OAB: {pt.oab}) [{pt.tipo_parte}]")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_oab_extraction())
