import asyncio
import httpx
import sys
import os
from datetime import datetime

# Define a URL do banco como SQLite ANTES de qualquer import de 'src'
# para garantir que o SQLAlchemy não inicialize com a URL do Postgres local.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///juridico.db"

sys.path.append(os.getcwd())

from src.database.connection import AsyncSessionLocal, create_tables
from src.database.models import Processo, Parte, Movimentacao
from sqlalchemy import select

CLOUD_API = "https://juridico-crawler-production.up.railway.app/api/integracao/processos?limit=1000"

async def sync():
    # 1. Garantir que as tabelas existem localmente
    print("[*] Verificando banco de dados local...")
    await create_tables()
    
    # 2. Buscar dados da nuvem
    print(f"[*] Buscando dados de: {CLOUD_API}")
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.get(CLOUD_API)
            r.raise_for_status()
            processos_cloud = r.json()
        except Exception as e:
            print(f"[ERRO] Falha ao conectar com a nuvem: {e}")
            return

    print(f"[OK] {len(processos_cloud)} processos encontrados na nuvem.")

    async with AsyncSessionLocal() as db:
        for p_data in processos_cloud:
            cnj = p_data["numero_cnj"]
            
            # Verificar se já existe
            res = await db.execute(select(Processo).where(Processo.numero_cnj == cnj))
            processo = res.scalar_one_or_none()
            
            if not processo:
                print(f"[+] Importando novo processo: {cnj}")
                processo = Processo(
                    numero_cnj=cnj,
                    tribunal=p_data.get("tribunal"),
                    grau=p_data.get("grau"),
                    vara=p_data.get("vara"),
                    comarca=p_data.get("comarca"),
                    classe_processual=p_data.get("classe_processual"),
                    assunto=p_data.get("assunto"),
                    situacao=p_data.get("situacao"),
                    data_distribuicao=datetime.strptime(p_data["data_distribuicao"], "%Y-%m-%d").date() if p_data.get("data_distribuicao") else None,
                )
                db.add(processo)
                await db.flush()
                
                # Importar partes
                for parte_data in p_data.get("partes", []):
                    parte = Parte(
                        processo_id=processo.id,
                        tipo_parte=parte_data["tipo_parte"],
                        nome=parte_data["nome"],
                        oab=parte_data.get("oab"),
                        polo=parte_data.get("polo")
                    )
                    db.add(parte)
                
                # Importar movimentações
                for mov_data in p_data.get("movimentacoes", []):
                    mov = Movimentacao(
                        processo_id=processo.id,
                        data_movimentacao=datetime.strptime(mov_data["data_movimentacao"], "%Y-%m-%d").date() if mov_data.get("data_movimentacao") else None,
                        descricao=mov_data.get("descricao")
                    )
                    db.add(mov)

        await db.commit()
    print("\n[SUCESSO] Sincronização concluída!")
    print("Agora você pode rodar 'local_dev_lite.ps1' para ver os dados no dashboard.")

if __name__ == "__main__":
    # Define a URL do banco como SQLite temporariamente se não estiver no ambiente
    if "DATABASE_URL" not in os.environ:
        os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///juridico.db"
    asyncio.run(sync())
