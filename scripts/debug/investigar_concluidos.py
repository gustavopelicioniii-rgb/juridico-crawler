import asyncio
import sys
import os
sys.path.append(os.getcwd())
from src.database.connection import AsyncSessionLocal
from sqlalchemy import text

async def debug_concluidos():
    oab = '361329'
    print(f"Investigando processos CONCLUIDOS para OAB {oab}...")
    
    async with AsyncSessionLocal() as db:
        # Busca processos do Sidney que estao como CONCLUIDO
        query = """
        SELECT p.id, p.numero_cnj, p.situacao, p.vara, p.comarca
        FROM processos p
        JOIN partes pt ON pt.processo_id = p.id
        WHERE pt.oab LIKE :oab AND p.situacao = 'CONCLUÍDO'
        GROUP BY p.id, p.numero_cnj, p.situacao, p.vara, p.comarca
        """
        rs = await db.execute(text(query), {"oab": f"%{oab}%"})
        processos = rs.fetchall()
        
        if not processos:
            print("Nenhum processo CONCLUIDO encontrado para este OAB no banco local.")
            return

        print(f"Encontrados {len(processos)} processos com status CONCLUIDO:")
        for p in processos:
            print(f"\n--- PROCESSO: {p.numero_cnj} ---")
            print(f"Vara/Comarca: {p.vara} / {p.comarca}")
            
            # Buscar as 3 ultimas movimentacoes para ver o motivo
            mov_query = "SELECT data_movimentacao, descricao FROM movimentacoes WHERE processo_id = :pid ORDER BY data_movimentacao DESC LIMIT 3"
            mrs = await db.execute(text(mov_query), {"pid": p.id})
            movs = mrs.fetchall()
            for m in movs:
                print(f"  [{m.data_movimentacao}] {m.descricao}")

if __name__ == "__main__":
    asyncio.run(debug_concluidos())
