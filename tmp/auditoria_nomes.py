import asyncio
import os
from src.crawlers.tjsp import TJSPCrawler

async def auditoria():
    async with TJSPCrawler() as c:
        oab = '361329'
        print(f"--- Auditoria TJSP OAB {oab} ---")
        procs = await c.buscar_por_oab(oab, 'SP')
        
        print(f"Total TJSP: {len(procs)}")
        for p in procs:
            advs = [pt.nome for pt in p.partes if pt.tipo_parte == 'Advogado']
            # Se não houver 'Advogado', talvez esteja como 'Advogada' ou outro label
            if not advs:
               advs = [pt.nome for pt in p.partes if pt.oab and oab in pt.oab]
            
            check = any('SIDNEY' in a.upper() or 'SYDNEY' in a.upper() for a in advs)
            print(f"CNJ: {p.numero_cnj} | Sidney? {check} | Advogados: {advs}")

if __name__ == "__main__":
    asyncio.run(auditoria())
