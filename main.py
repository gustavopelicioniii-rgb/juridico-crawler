"""
API REST - Monitoramento de Processos Jurídicos + Autenticação Multi-Tenant
Fase 1: Backend com JWT + PostgreSQL + RLS
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, router as auth_router
from src.api.rate_limit import limiter
from src.config import settings
from src.database.connection import AsyncSessionLocal, create_tables
from src.database.models import Notificacao, Prazo, Processo


def _configure_structlog() -> None:
    """Pipeline único para logging tanto do stdlib quanto do structlog."""
    level = logging.DEBUG if settings.api_debug else logging.INFO
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_configure_structlog()
logger = structlog.get_logger(__name__)

scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown da aplicação."""
    global scheduler

    logger.info("api.startup", phase="begin", version="1.0.0", env=settings.api_environment)

    try:
        await create_tables()
        logger.info("api.startup", phase="db_ready")
    except Exception:
        logger.exception("api.startup.failure")
        raise

    # Inicia o scheduler somente se explicitamente habilitado (evita duplicar
    # jobs quando múltiplos workers do Uvicorn/Gunicorn subirem a mesma app).
    scheduler_enabled = getattr(settings, "scheduler_enabled", True)
    if scheduler_enabled:
        try:
            from src.scheduler.jobs import criar_scheduler

            scheduler = criar_scheduler()
            scheduler.start()
            logger.info(
                "api.startup",
                phase="scheduler_started",
                cron=f"{settings.scheduler_cron_hora:02d}:{settings.scheduler_cron_minuto:02d}",
            )
        except Exception:
            logger.exception("api.startup.scheduler_failure")
    else:
        logger.info("api.startup", phase="scheduler_disabled")

    logger.info("api.startup", phase="ready")

    yield

    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
            logger.info("api.shutdown", phase="scheduler_stopped")
        except Exception:
            logger.exception("api.shutdown.scheduler_failure")

    logger.info("api.shutdown", phase="done")


app = FastAPI(
    title="Sistema Jurídico",
    description="Fase 1: Backend Multi-Tenant",
    version="1.0.0",
    lifespan=lifespan,
)

# ----------------------------------------------------------------------------
# Middleware & error handlers
# ----------------------------------------------------------------------------
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)


# ============================================================================
# DEPENDENCIES
# ============================================================================

async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Garante que o usuário autenticado é admin."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operação restrita a administradores",
        )
    return current_user


# ============================================================================
# HEALTH & STATUS
# ============================================================================

@app.get("/health", tags=["system"])
async def health():
    """Health check da API."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
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
    except Exception:
        logger.exception("processos.listar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao listar processos")


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
    except Exception:
        logger.exception("processos.obter.failure", processo_id=processo_id)
        raise HTTPException(status_code=500, detail="Erro interno ao obter processo")


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
        query = (
            select(Notificacao)
            .order_by(Notificacao.criado_em.desc())
            .offset(skip)
            .limit(limit)
        )
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
    except Exception:
        logger.exception("notificacoes.listar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao listar notificações")


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
    except Exception:
        logger.exception("prazos.listar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao listar prazos")


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
                except Exception:
                    logger.warning(
                        "processos.salvar.failure",
                        numero_cnj=proc.numero_cnj,
                    )
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
    except Exception:
        logger.exception(
            "busca.oab.failure",
            numero_oab=req.numero_oab,
            uf_oab=req.uf_oab,
        )
        raise HTTPException(status_code=500, detail="Erro interno ao buscar por OAB")


@app.get("/api/buscar/cnj/{numero_cnj}", tags=["busca"])
async def buscar_por_cnj(
    numero_cnj: str,
    tribunal: Optional[str] = Query(None),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Busca um processo específico pelo número CNJ via DataJud."""
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
            "partes": [
                {"nome": p.nome, "tipo": p.tipo_parte, "polo": p.polo}
                for p in proc.partes
            ],
            "movimentacoes": [
                {"data": str(m.data_movimentacao), "descricao": m.descricao}
                for m in proc.movimentacoes[:20]
            ],
            "valor_causa": float(proc.valor_causa) if proc.valor_causa else None,
            "score_auditoria": proc.score_auditoria,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("busca.cnj.failure", numero_cnj=numero_cnj)
        raise HTTPException(status_code=500, detail="Erro interno ao buscar por CNJ")


# ============================================================================
# MIGRATIONS (requer admin)
# ============================================================================

class MigrationResponse(BaseModel):
    status: str
    migrations_run: list[str]
    errors: list[str]


@app.post("/api/migrations/run", tags=["system"], response_model=MigrationResponse)
async def run_migrations(_: dict = Depends(require_admin)):
    """
    Executa todas as migrations do banco de dados.
    Requer usuário autenticado com role=admin.
    """
    import os
    from pathlib import Path

    import sqlparse
    from sqlalchemy import text

    migrations_dir = Path(__file__).parent / "src" / "database" / "migrations"
    migration_files = sorted(
        f for f in os.listdir(migrations_dir) if f.endswith(".sql")
    )

    migrations_run: list[str] = []
    errors: list[str] = []

    async with AsyncSessionLocal() as session:
        for filename in migration_files:
            try:
                filepath = migrations_dir / filename
                sql_content = filepath.read_text(encoding="utf-8")

                # sqlparse entende triggers, DO blocks, funções e strings com `;`
                statements = [
                    stmt.strip()
                    for stmt in sqlparse.split(sql_content)
                    if stmt.strip()
                ]

                for statement in statements:
                    await session.execute(text(statement))

                await session.commit()
                migrations_run.append(filename)
                logger.info("migrations.apply.success", file=filename)
            except Exception:
                await session.rollback()
                errors.append(filename)
                logger.exception("migrations.apply.failure", file=filename)

    return MigrationResponse(
        status="ok" if not errors else "completed_with_errors",
        migrations_run=migrations_run,
        errors=errors,
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
                <div class="endpoint">POST /api/buscar/oab</div>
                <div class="endpoint">GET /api/buscar/cnj/{numero_cnj}</div>
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
