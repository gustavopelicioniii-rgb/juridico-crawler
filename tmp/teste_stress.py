import asyncio
import time
from src.crawlers.orquestrador import OrquestradorNativo

async def teste_estresse():
    print("--- INICIANDO TESTE COM 20 OABs (VARREDURA NACIONAL) ---")
    start = time.time()
    
    o = OrquestradorNativo()
    
    # Gerando 20 OABs sequenciais na faixa dos 200.000 para pegarmos processos
    oab_base = 250000
    
    resultados = []
    erros = 0
    
    for i in range(20):
        oab = str(oab_base + i)
        print(f"[{i+1}/20] Buscando OAB {oab}/SP...")
        try:
            # Buscando sem filtro de nome brutal para ver o número bruto retornado
            procs = await o.buscar_por_oab(oab, 'SP')
            print(f"       -> Sucesso! Encontrados: {len(procs)} processos unicos.")
            resultados.append(len(procs))
        except Exception as e:
            print(f"       -> [ERRO] OAB {oab} falhou: {e}")
            erros += 1
            
    print("\n" + "="*40)
    print("--- RESUMO DO TESTE DE ROBUSTEZ ---")
    print(f"OABs processadas com sucesso: {20 - erros}")
    print(f"Falhas Críticas (Erros): {erros}")
    print(f"Total de processos minerados: {sum(resultados)}")
    print(f"Tempo total de execução: {time.time() - start:.2f} segundos")
    print("="*40)

if __name__ == "__main__":
    asyncio.run(teste_estresse())
