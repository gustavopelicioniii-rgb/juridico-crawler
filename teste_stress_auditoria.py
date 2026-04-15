import asyncio
import time
import random
import os
import sys

sys.path.append(os.getcwd())

from src.crawlers.orquestrador import OrquestradorNativo

async def auditar_oab(o, numero_oab, uf):
    try:
        # Busca sem filtros adicionais para captar o máximo
        procs = await o.buscar_por_oab(numero_oab, uf)
        notas = [p.score_auditoria for p in procs if getattr(p, 'score_auditoria', None) is not None]
        media = sum(notas)/len(notas) if notas else 0
        return numero_oab, len(procs), media, None
    except Exception as e:
        return numero_oab, 0, 0, str(e)

async def teste_estresse():
    print("==========================================================")
    print("--- INICIANDO TESTE DE ESTRESSE MASSIVO COM AUDITORIA ATIVA ---")
    print("==========================================================")
    print("Nota: Como não existe uma lista pública nacional separada por cidade,")
    print("estamos simulando a carga de uma cidade como Atibaia gerando uma amostragem")
    print("aleatória massiva de 50 registros válidos da OAB/SP da mesma faixa.\n")
    
    start = time.time()
    o = OrquestradorNativo()
    
    # Gerando 50 OABs aleatórias entre os inscritos de SP para bater nos tribunais em força bruta
    # (Usaremos uma faixa grande para pegar OABs antigas e novas)
    oabs = [str(random.randint(250000, 480000)) for _ in range(50)]
    
    print(f"Disparando {len(oabs)} pesquisas *SIMULTÂNEAS* no Orquestrador...")
    print("Os dados serão raspados, validados pelo novo robô em tempo real e consolidados...\n")
    
    # Batch de execução assíncrona total (Para fritar e testar os limites do crawler/rate limit)
    tasks = [auditar_oab(o, oab, "SP") for oab in oabs]
    
    resultados = await asyncio.gather(*tasks)
    
    sucessos = 0
    erros_sistema = 0
    total_procs = 0
    soma_medias = 0
    advogados_com_processo = 0
    
    for oab, qtd, media, erro in resultados:
        if erro:
            print(f"[ERRO] OAB {oab}: Falha na Busca -> {erro}")
            erros_sistema += 1
        else:
            if qtd > 0:
                print(f"[OK] OAB {oab}: {qtd:03d} processos recuperados | Confiabilidade dos Dados: {media:.1f}/100")
                sucessos += 1
                total_procs += qtd
                advogados_com_processo += 1
                soma_medias += media
            else:
                # OAB pode ser inativa, estar no formato incorreto ou advogado não atua em SP recentemente.
                print(f"[AVISO] OAB {oab}: 0 processos associados.")
                sucessos += 1 
                
    
    print("\n" + "="*60)
    print("--- RELATÓRIO DO TESTE DE ESTRESSE & VALIDAÇÃO ---")
    print("="*60)
    print(f"Total de OABs Processadas Simultaneamente: {len(oabs)}")
    print(f"Falhas Intermitentes do Tribunal (Timeouts/Erros): {erros_sistema}")
    print(f"Advogados com pelo menos 1 processo: {advogados_com_processo}")
    print(f"Volume Total Extracado e Auditado: {total_procs} processos únicos")
    
    if advogados_com_processo > 0 and total_procs > 0:
        media_geral = soma_medias / advogados_com_processo
        print(f"==========================================================")
        print(f"--- NOTA DE CONFIABILIDADE GLOBAL SOB ESTRESSE: {media_geral:.1f} / 100 ---")
        print(f"==========================================================")
        
    print(f"Tempo Total do Benchmark: {time.time() - start:.2f} segundos")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(teste_estresse())
