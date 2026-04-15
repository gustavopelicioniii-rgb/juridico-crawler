import asyncio
import time
import logging
import random
from sqlalchemy.ext.asyncio import AsyncSession
from src.database.connection import AsyncSessionLocal
from src.crawlers.orquestrador import OrquestradorNativo
from src.services.processo_service import ProcessoService

# Desativar logs excessivos para ver apenas o progresso
logging.getLogger("src.crawlers.tjsp").setLevel(logging.WARNING)
logging.getLogger("src.crawlers.pje").setLevel(logging.WARNING)

async def bot_loader(oab: str, uf: str, semaphore: asyncio.Semaphore):
    async with semaphore:
        o = OrquestradorNativo()
        try:
            print(f"[*] Bot alocado para OAB {oab}/{uf}...")
            # Um pequeno delay aleatório para evitar colisão no firewall dos tribunais
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
            procs = await o.buscar_por_oab(oab, uf)
            if not procs:
                print(f"[!] OAB {oab}: Zero processos.")
                return 0, 0
            
            async with AsyncSessionLocal() as db:
                svc = ProcessoService(db)
                
                # Registrando os resultados massivos no banco
                stats = await svc.salvar_processos(procs)
                
                # Auto Alimentar o Catálogo de Inteligência
                await svc.registrar_advogado_descoberto(
                    numero_oab=oab,
                    uf=uf,
                    nome_completo=f"Advogado Descoberto {oab}",
                    total_processos=len(procs)
                )
                await db.commit()
                print(f"[+] OAB {oab} CONCLUÍDA: {len(procs)} extraídos | {stats.get('novos', 0)} novos no Banco!")
                return len(procs), stats.get("novos", 0)
        except Exception as e:
            print(f"[ERROR] OAB {oab} abortada: {e}")
            return 0, 0

async def mass_populate(start_oab=300000, max_bots=3, total_oabs=50):
    print("\n" + "🔥"*20)
    print(f" INICIANDO MASS POPULATE ({total_oabs} OABs)")
    print(f" Exército de Bots simultâneos: {max_bots}")
    print("🔥"*20 + "\n")
    
    start = time.time()
    
    # Criando o controle de concorrência massiva
    semaphore = asyncio.Semaphore(max_bots)
    tasks = []
    
    # Gerando o exército de tarefas
    for i in range(total_oabs):
        oab = str(start_oab + i)
        tasks.append(bot_loader(oab, 'SP', semaphore))
        
    resultados = await asyncio.gather(*tasks)
    
    total_encontrado = sum(r[0] for r in resultados if r)
    total_novos_salvos = sum(r[1] for r in resultados if r)
    
    print("\n" + "="*50)
    print("--- 🏁 RELATÓRIO DE POPULAÇÃO MASSIVA ---")
    print(f"OABs varridas no Brasil inteiro: {total_oabs}")
    print(f"Processos Únicos Encontrados: {total_encontrado}")
    print(f"Novos Cadastros Gravações DB: {total_novos_salvos}")
    print(f"Velocidade do Sistema: {time.time() - start:.2f} segundos")
    print("="*50)

if __name__ == "__main__":
    # Teste de carga: 50 OABs paralelas usando 3 Bots (representa 150 requests simultâneos)
    asyncio.run(mass_populate(start_oab=300000, max_bots=3, total_oabs=50))
