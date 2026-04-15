
import asyncio
import sys
import os
from collections import Counter

# Ajustar path
sys.path.append(os.getcwd())

from src.crawlers.orquestrador import OrquestradorNativo

async def diagnostico():
    print("--- DIAGNÓSTICO: OAB 361329 + NOME 'Sidney' ---")
    o = OrquestradorNativo()
    
    # Simulando exatamente a busca do usuário
    procs = await o.buscar_por_oab('361329', 'SP', nome_advogado='Sidney')
    
    print(f"\nTotal encontrado: {len(procs)}")
    
    status_map = {}
    for p in procs:
        status = p.situacao or "EM ANDAMENTO"
        if status not in status_map:
            status_map[status] = []
        status_map[status].append(p.numero_cnj)
        
    print("\nResumo de Status:")
    for status, cnjs in status_map.items():
        print(f" - {status}: {len(cnjs)}")
        if status.upper() in ["CONCLUÍDO", "CONCLUIDO", "EXTINTO", "ENCERRADO", "BAIXADO"]:
            for cnj in cnjs:
                print(f"   [!] {cnj}")

if __name__ == "__main__":
    asyncio.run(diagnostico())
