
import asyncio
import sys
import os

# Ajustar o path para os módulos do projeto
sys.path.append(os.getcwd())

from src.database.connection import AsyncSessionLocal
from src.database.models import Parte
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        # Busca como o nome está escrito para esta OAB
        stmt = select(Parte.nome).where(Parte.oab.ilike('%361329%')).distinct()
        r = await db.execute(stmt)
        names = r.scalars().all()
        print(f"Nomes encontrados para 361329: {names}")

if __name__ == "__main__":
    asyncio.run(check())
