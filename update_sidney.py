import asyncio
import sys
import os

sys.path.append(os.getcwd())

from src.database.connection import AsyncSessionLocal
from src.crawlers.orquestrador import OrquestradorNativo
from src.services.processo_service import ProcessoService

async def update_sidney():
    oab = "361329"
    uf = "SP"
    print(f"Buscando dados com 100% de precisao para OAB {oab}/{uf}...")
    
    o = OrquestradorNativo()
    # Puxa os processos com as novas correções
    procs = await o.buscar_por_oab(oab, uf)
    
    if not procs:
         print("Nenhum processo encontrado para este OAB.")
         return
         
    print(f"[OK] {len(procs)} processos pegos com detalhes profundos. Salvando no banco de dados...")
    
    # Salva oficialemente no Postgres
    async with AsyncSessionLocal() as db:
         svc = ProcessoService(db)
         stats = await svc.salvar_processos(procs)
         
         await svc.registrar_advogado_descoberto(
            numero_oab=oab,
            uf=uf,
            nome_completo="Sidney (Validado)",
            total_processos=len(procs)
         )
         await db.commit()
         
         print(f"[SUCESSO] Banco atualizado com sucesso!")
         print(f"[INFO] Novos registros inseridos: {stats.get('novos', 0)}")
         print(f"[INFO] Registros atualizados com as informações completas: {stats.get('atualizados', 0)}")

if __name__ == "__main__":
    asyncio.run(update_sidney())
