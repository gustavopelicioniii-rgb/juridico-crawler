"""
API REST - Monitoramento de Processos Jurídicos + Autenticação Multi-Tenant
Fase 1: Backend com JWT + PostgreSQL + RLS
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime

logger = logging.getLogger(__name__)

from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional

from src.database.connection import create_tables
from src.api.auth import router as auth_router
from src.database.connection import AsyncSessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.database.models import Processo, Notificacao, Prazo

scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown da aplicação."""
    print("\n" + "="*70)
    print("🚀 INICIANDO API - FASE 1 MULTI-TENANT")
    print("="*70)

    try:
        await create_tables()
        print("✅ Banco de dados: OK")
        print("✅ Auth router: OK")
        print("="*70 + "\n")
    except Exception as e:
        print(f"❌ Erro ao iniciar: {e}")
        raise

    yield

    print("\n✅ API finalizada")


app = FastAPI(
    title="Sistema Jurídico",
    description="Fase 1: Backend Multi-Tenant",
    version="1.0.0",
    lifespan=lifespan,
)

# Incluir router de autenticação
app.include_router(auth_router)


# ============================================================================
# HEALTH & STATUS
# ============================================================================

@app.get("/health", tags=["system"])
async def health():
    """Health check da API."""
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }


# ============================================================================
# PROCESSOS
# ============================================================================

@app.get("/api/processos", tags=["processos"])
async def listar_processos(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Lista processos com paginação."""
    try:
        query = select(Processo).offset(skip).limit(limit)
        result = await session.execute(query)
        processos = result.scalars().all()

        count_query = select(func.count(Processo.id))
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        return {
            "data": [
                {
                    "id": p.id,
                    "numero_cnj": p.numero_cnj,
                    "tribunal": p.tribunal,
                    "situacao": p.situacao,
                }
                for p in processos
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/processos/{processo_id}", tags=["processos"])
async def obter_processo(
    processo_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Detalhes de um processo."""
    try:
        resultado = await session.execute(
            select(Processo).where(Processo.id == processo_id)
        )
        processo = resultado.scalar_one_or_none()

        if not processo:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        return {
            "id": processo.id,
            "numero_cnj": processo.numero_cnj,
            "tribunal": processo.tribunal,
            "vara": processo.vara,
            "situacao": processo.situacao,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# NOTIFICAÇÕES
# ============================================================================

@app.get("/api/notificacoes", tags=["notificacoes"])
async def listar_notificacoes(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Lista notificações."""
    try:
        query = select(Notificacao).order_by(Notificacao.criado_em.desc()).offset(skip).limit(limit)
        result = await session.execute(query)
        notificacoes = result.scalars().all()

        count_query = select(func.count(Notificacao.id))
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        return {
            "data": [
                {
                    "id": n.id,
                    "tipo": n.tipo,
                    "resumo": n.resumo,
                    "lida": n.lida,
                }
                for n in notificacoes
            ],
            "total": total,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PRAZOS
# ============================================================================

@app.get("/api/prazos", tags=["prazos"])
async def listar_prazos(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Lista prazos."""
    try:
        query = select(Prazo).order_by(Prazo.data_vencimento).offset(skip).limit(limit)
        result = await session.execute(query)
        prazos = result.scalars().all()

        count_query = select(func.count(Prazo.id))
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        return {
            "data": [
                {
                    "id": p.id,
                    "tipo_prazo": p.tipo_prazo,
                    "data_vencimento": str(p.data_vencimento),
                    "cumprido": p.cumprido,
                }
                for p in prazos
            ],
            "total": total,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BUSCA POR OAB
# ============================================================================

class BuscaOABRequest(BaseModel):
    numero_oab: str
    uf_oab: str
    tribunais: Optional[list[str]] = None
    salvar_bd: bool = True


@app.post("/api/buscar/oab", tags=["busca"])
async def buscar_por_oab(
    req: BuscaOABRequest,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """
    Busca processos por número de OAB em todos os tribunais disponíveis
    e opcionalmente persiste os resultados no banco de dados.
    """
    from src.crawlers.orquestrador import OrquestradorNativo
    from src.services.processo_service import ProcessoService

    try:
        orq = OrquestradorNativo()
        processos = await orq.buscar_por_oab(
            numero_oab=req.numero_oab,
            uf_oab=req.uf_oab,
            tribunais=req.tribunais,
        )

        salvos = 0
        if req.salvar_bd and processos:
            svc = ProcessoService(session)
            for proc in processos:
                try:
                    await svc.salvar_processo(proc)
                    salvos += 1
                except Exception as e:
                    logger.warning("Erro ao salvar processo %s: %s", proc.numero_cnj, e)
            await session.commit()

        return {
            "oab": f"{req.numero_oab}/{req.uf_oab}",
            "total": len(processos),
            "salvos_bd": salvos,
            "processos": [
                {
                    "numero_cnj": p.numero_cnj,
                    "tribunal": p.tribunal,
                    "vara": p.vara,
                    "classe_processual": p.classe_processual,
                    "situacao": p.situacao,
                    "partes": len(p.partes),
                    "movimentacoes": len(p.movimentacoes),
                    "valor_causa": float(p.valor_causa) if p.valor_causa else None,
                    "score_auditoria": p.score_auditoria,
                }
                for p in processos
            ],
        }
    except Exception as e:
        logger.error("Erro na busca por OAB %s/%s: %s", req.numero_oab, req.uf_oab, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/buscar/cnj/{numero_cnj}", tags=["busca"])
async def buscar_por_cnj(
    numero_cnj: str,
    tribunal: Optional[str] = Query(None),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """
    Busca um processo específico pelo número CNJ via DataJud.
    """
    from src.crawlers.datajud import DataJudCrawler
    from src.services.processo_service import ProcessoService

    try:
        async with DataJudCrawler() as crawler:
            proc = await crawler.buscar_processo(
                numero_cnj=numero_cnj,
                tribunal=tribunal or "tjsp",
                usar_ai_parser=False,
            )

        if not proc:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        svc = ProcessoService(session)
        await svc.salvar_processo(proc)
        await session.commit()

        return {
            "numero_cnj": proc.numero_cnj,
            "tribunal": proc.tribunal,
            "vara": proc.vara,
            "classe_processual": proc.classe_processual,
            "situacao": proc.situacao,
            "partes": [{"nome": p.nome, "tipo": p.tipo_parte, "polo": p.polo} for p in proc.partes],
            "movimentacoes": [
                {"data": str(m.data_movimentacao), "descricao": m.descricao}
                for m in proc.movimentacoes[:20]
            ],
            "valor_causa": float(proc.valor_causa) if proc.valor_causa else None,
            "score_auditoria": proc.score_auditoria,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Erro na busca por CNJ %s: %s", numero_cnj, e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MIGRATIONS
# ============================================================================

class MigrationResponse(BaseModel):
    status: str
    migrations_run: list[str]
    errors: list[str]

@app.post("/api/migrations/run", tags=["system"], response_model=MigrationResponse)
async def run_migrations():
    """
    Executa todas as migrations do banco de dados.
    Use para inicializar o banco ou aplicar updates.
    """
    import os
    from pathlib import Path
    
    migrations_dir = Path(__file__).parent / "src" / "database" / "migrations"
    migration_files = sorted([f for f in os.listdir(migrations_dir) if f.endswith('.sql')])
    
    migrations_run = []
    errors = []
    
    async with AsyncSessionLocal() as session:
        for filename in migration_files:
            try:
                filepath = migrations_dir / filename
                sql_content = filepath.read_text()
                
                # Executa cada statement separadamente
                for statement in sql_content.split(';'):
                    statement = statement.strip()
                    if statement:
                        await session.execute(statement)
                
                await session.commit()
                migrations_run.append(filename)
                logger.info(f"Migration {filename} executada com sucesso")
            except Exception as e:
                await session.rollback()
                errors.append(f"{filename}: {str(e)}")
                logger.error(f"Erro na migration {filename}: {e}")
    
    return MigrationResponse(
        status="ok" if not errors else "completed_with_errors",
        migrations_run=migrations_run,
        errors=errors
    )

# ============================================================================
# DASHBOARD
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Dashboard da API."""
    return """
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Sistema Jurídico - Fase 1</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1000px; margin: 0 auto; }
            h1 { color: white; text-align: center; margin-bottom: 30px; }
            .card {
                background: white;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            }
            .card h2 { color: #667eea; margin-bottom: 10px; }
            .endpoint {
                background: #f5f5f5;
                padding: 10px;
                margin: 5px 0;
                border-left: 3px solid #667eea;
                font-family: monospace;
                font-size: 14px;
            }
            .status { color: #28a745; font-weight: bold; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Sistema de Monitoramento Jurídico - Fase 1</h1>

            <div class="card">
                <h2>✅ Status</h2>
                <p><span class="status">API Online</span> - Pronta para uso</p>
            </div>

            <div class="card">
                <h2>🔐 Autenticação</h2>
                <div class="endpoint">POST /api/auth/login</div>
                <div class="endpoint">POST /api/auth/refresh</div>
                <div class="endpoint">POST /api/auth/register</div>
                <div class="endpoint">GET /api/auth/me</div>
                <div class="endpoint">POST /api/auth/change-password</div>
            </div>

            <div class="card">
                <h2>📊 Endpoints de Dados</h2>
                <div class="endpoint">GET /api/processos</div>
                <div class="endpoint">GET /api/processos/{id}</div>
                <div class="endpoint">GET /api/notificacoes</div>
                <div class="endpoint">GET /api/prazos</div>
            </div>

            <div class="card">
                <h2>📖 Documentação</h2>
                <div class="endpoint"><a href="/docs" style="color: #667eea; text-decoration: none;">📘 Swagger UI (Interativo)</a></div>
                <div class="endpoint"><a href="/redoc" style="color: #667eea; text-decoration: none;">📕 ReDoc</a></div>
            </div>
        </div>
    </body>
    </html>
    """
