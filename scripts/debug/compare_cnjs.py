import asyncio
import sys
import os

sys.path.append(os.getcwd())

from src.database.connection import AsyncSessionLocal
from src.database.models import Processo, Parte
from sqlalchemy import select

async def get_cnjs():
    async with AsyncSessionLocal() as db:
        # Busca processos que tenham Sidney (361329) nas partes
        result = await db.execute(
            select(Processo.numero_cnj)
            .join(Parte, Parte.processo_id == Processo.id)
            .where(Parte.oab.ilike('%361329%'))
        )
        cnjs = sorted(list(set(result.scalars().all())))
        print(f"Total no banco: {len(cnjs)}")
        for c in cnjs:
            print(c)

if __name__ == "__main__":
    asyncio.run(get_cnjs())
