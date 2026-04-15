import asyncio
import sys
import os

sys.path.append(os.getcwd())

from src.database.connection import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as db:
        rs = await db.execute(text('SELECT situacao, count(*) FROM processos GROUP BY situacao'))
        rows = rs.fetchall()
        print("Status dos processos no DB:")
        for row in rows:
            print(f"- {row[0]}: {row[1]}")

asyncio.run(main())
