import asyncio
import sys
import os
sys.path.append(os.getcwd())
try:
    from src.database.connection import AsyncSessionLocal
    from sqlalchemy import text
except ImportError:
    print("Imports falharam!")
    exit(1)

async def main():
    async with AsyncSessionLocal() as db:
        query = """
        SELECT p.numero_cnj, p.situacao, COUNT(m.id) as qtd_movs 
        FROM processos p 
        LEFT JOIN movimentacoes m ON m.processo_id = p.id 
        JOIN advogado_processo ap ON ap.processo_id = p.id 
        JOIN advogado_catalog a ON a.id = ap.advogado_id 
        WHERE a.numero_oab = '361329' 
        GROUP BY p.numero_cnj, p.situacao
        """
        rs = await db.execute(text(query))
        rows = rs.fetchall()
        print(f"Total for Sidney: {len(rows)}")
        for row in rows:
            print(f"- {row[0]}: {row[1]} (movs: {row[2]})")

if __name__ == "__main__":
    asyncio.run(main())
