import asyncio
from src.crawlers.eproc import EProcCrawler

async def check_federal():
    async with EProcCrawler() as c:
        oab = '361329'
        print(f"--- Buscando OAB {oab} no TRF3 (Federal) ---")
        procs = await c.buscar_por_oab(oab, 'SP', tribunais=['trf3'])
        print(f"Total Federal (TRF3): {len(procs)}")
        for p in procs:
            print(f"- CNJ: {p.numero_cnj}")

if __name__ == "__main__":
    asyncio.run(check_federal())
