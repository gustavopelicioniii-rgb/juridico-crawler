import asyncio
from src.crawlers.orquestrador import OrquestradorNativo

async def master_scan():
    orc = OrquestradorNativo()
    oab = '361329'
    uf = 'SP'
    print(f"--- Master Scan OAB {oab}/{uf} ---")
    
    # Vamos rodar a busca completa e ver o que o Orquestrador consolida
    processos = await orc.buscar_por_oab(oab, uf)
    
    print(f"\nTotal Geral Consolidado: {len(processos)}")
    
    # Contagem por tribunal
    counts = {}
    for p in processos:
        counts[p.tribunal] = counts.get(p.tribunal, 0) + 1
        
    for trib, count in counts.items():
        print(f"- {trib.upper()}: {count} processos")

if __name__ == "__main__":
    asyncio.run(master_scan())
