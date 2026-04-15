import asyncio
from src.database.connection import AsyncSessionLocal
from src.database.models import Processo, Parte, Movimentacao
from sqlalchemy import select, func

async def diag():
    async with AsyncSessionLocal() as db:
        p_count = await db.execute(select(func.count(Processo.id)))
        part_count = await db.execute(select(func.count(Parte.id)))
        mov_count = await db.execute(select(func.count(Movimentacao.id)))
        print(f"DATABASE DIAGNOSTIC:")
        print(f"- Processos: {p_count.scalar()}")
        print(f"- Partes:    {part_count.scalar()}")
        print(f"- Movs:      {mov_count.scalar()}")
        
        last_ps = await db.execute(select(Processo).limit(5).order_by(Processo.id.desc()))
        for p in last_ps.scalars().all():
            print(f"  > [CNJ: {p.numero_cnj}] [Trib: {p.tribunal}]")

if __name__ == "__main__":
    asyncio.run(diag())
