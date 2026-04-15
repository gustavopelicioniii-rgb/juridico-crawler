import asyncio
import sys
import os
sys.path.append(os.getcwd())
from src.database.connection import AsyncSessionLocal
from sqlalchemy import text

async def check_all_sidney_statuses():
    oab = '361329'
    async with AsyncSessionLocal() as db:
        query = """
        SELECT p.situacao, count(*)
        FROM processos p
        JOIN partes pt ON pt.processo_id = p.id
        WHERE pt.oab LIKE :oab
        GROUP BY p.situacao
        """
        rs = await db.execute(text(query), {"oab": f"%{oab}%"})
        rows = rs.fetchall()
        print(f"Status dos processos do Sidney (OAB {oab}):")
        for row in rows:
            print(f"- {row[0]}: {row[1]}")

if __name__ == "__main__":
    asyncio.run(check_all_sidney_statuses())
