
import asyncio
import json
import logging
import sys
import os

# Ajustar o path para encontrar os módulos do projeto
sys.path.append(os.getcwd())

from src.crawlers.orquestrador import OrquestradorNativo

async def diagnostico_sydney():
    print("--- INICIANDO DIAGNÓSTICO: DR. SYDNEY (361329 SP) ---")
    o = OrquestradorNativo()
    
    # Nome alvo para o filtro
    nome_alvo = "Sidney"
    
    print(f"Buscando processos para: {nome_alvo}...")
    procs = await o.buscar_por_oab('361329', 'SP', nome_advogado=nome_alvo)
    
    print(f"\nTotal encontrado: {len(procs)}")
    
    status_counts = {}
    concluidos = []
    
    for p in procs:
        status = p.situacao or "EM ANDAMENTO"
        status_counts[status] = status_counts.get(status, 0) + 1
        if status.upper() in ["CONCLUÍDO", "CONCLUIDO", "ENCERRADO", "EXTINTO", "BAIXADO"]:
            concluidos.append(p)
            
    print("\nResumo de Status:")
    for s, c in status_counts.items():
        print(f" - {s}: {c}")
        
    if concluidos:
        print("\nDetalhe dos Concluídos:")
        for p in concluidos:
            print(f" -> CNJ: {p.numero_cnj} | Status: {p.situacao}")
    else:
        print("\nNenhum processo marcado como concluído nesta varredura.")

if __name__ == "__main__":
    asyncio.run(diagnostico_sydney())
