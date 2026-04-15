import asyncio
import sys
import os
sys.path.append(os.getcwd())
from src.database.connection import AsyncSessionLocal
from sqlalchemy import text

async def check_process():
    cnj = '1003032-46.2023.8.26.0048'
    async with AsyncSessionLocal() as db:
        rs = await db.execute(text("SELECT id, numero_cnj, situacao FROM processos WHERE numero_cnj = :cnj"), {"cnj": cnj})
        p = rs.fetchone()
        if p:
            print(f"Processo: {p.numero_cnj} | Situacao: {p.situacao}")
            
            # Check parts
            rs_pts = await db.execute(text("SELECT nome, oab, tipo_parte FROM partes WHERE processo_id = :pid"), {"pid": p.id})
            pts = rs_pts.fetchall()
            print("Partes:")
            for pt in pts:
                print(f"  - {pt.nome} (OAB: {pt.oab}) [{pt.tipo_parte}]")
        else:
            print(f"Processo {cnj} nao encontrado no DB!")

if __name__ == "__main__":
    asyncio.run(check_process())
