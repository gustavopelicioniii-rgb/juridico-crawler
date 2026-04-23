
import asyncio
from src.database.connection import AsyncSessionLocal
from src.database.models import Processo, Parte
from sqlalchemy import select
from sqlalchemy.orm import selectinload

async def check():
    async with AsyncSessionLocal() as db:
        # Busca processos relacionados à OAB 202030
        stmt = select(Processo).join(Parte).where(Parte.oab.ilike('%202030%')).options(selectinload(Processo.partes))
        result = await db.execute(stmt)
        procs = result.scalars().unique().all()
        
        print(f"\n--- RELATÓRIO DE NOMES PARA OAB 202030 ---")
        print(f"Total de processos no banco: {len(procs)}")
        
        for p in procs:
            print(f"\nProcesso: {p.numero_cnj} ({p.tribunal})")
            nomes = [pt.nome for pt in p.partes]
            print(f"Partes/Advogados encontrados: {nomes}")

if __name__ == "__main__":
    asyncio.run(check())
