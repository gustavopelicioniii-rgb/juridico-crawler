import asyncio
from src.crawlers.pje import PJeCrawler, TODOS_TRIBUNAIS_PJE

async def check_pje():
    async with PJeCrawler(verify_ssl=False) as c:
        oab = '361329'
        uf = 'SP'
        print(f"--- Buscando OAB {oab}/{uf} no Ecossistema PJe (Trabalho/Federal) ---")
        
        # Vamos buscar em todos os tribunais conhecidos pelo PJe no sistema
        print(f"Alvos PJe: {len(TODOS_TRIBUNAIS_PJE)} tribunais")
        
        procs = await c.buscar_por_oab(oab, uf, tribunais=TODOS_TRIBUNAIS_PJE)
        
        print(f"\nTotal PJe: {len(procs)}")
        
        counts = {}
        for p in procs:
            counts[p.tribunal] = counts.get(p.tribunal, 0) + 1
            
        for trib, count in counts.items():
            print(f"- {trib.upper()}: {count} processos")

if __name__ == "__main__":
    asyncio.run(check_pje())
