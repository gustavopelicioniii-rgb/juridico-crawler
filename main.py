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
from sqlalchemy import and_, func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, router as auth_router
from src.api.rate_limit import limiter
from src.config import settings
from src.database.connection import AsyncSessionLocal, create_tables
from src.database.models import Monitoramento, Notificacao, Prazo, Processo


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
    tribunal: Optional[str] = Query(None),
    situacao: Optional[str] = Query(None),
    score_min: Optional[int] = Query(None, ge=0, le=100),
    numero_cnj: Optional[str] = Query(None),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Lista processos com filtros."""
    try:
        query = select(Processo)
        count_query = select(func.count(Processo.id))

        if tribunal:
            query = query.where(Processo.tribunal.ilike(f"%{tribunal}%"))
            count_query = count_query.where(Processo.tribunal.ilike(f"%{tribunal}%"))
        if situacao:
            query = query.where(Processo.situacao.ilike(f"%{situacao}%"))
            count_query = count_query.where(Processo.situacao.ilike(f"%{situacao}%"))
        if score_min is not None:
            query = query.where(Processo.score_auditoria >= score_min)
            count_query = count_query.where(Processo.score_auditoria >= score_min)
        if numero_cnj:
            query = query.where(Processo.numero_cnj.ilike(f"%{numero_cnj}%"))
            count_query = count_query.where(Processo.numero_cnj.ilike(f"%{numero_cnj}%"))

        query = query.order_by(Processo.criado_em.desc()).offset(skip).limit(limit)
        result = await session.execute(query)
        processos = result.scalars().all()

        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        return {
            "data": [
                {
                    "id": p.id,
                    "numero_cnj": p.numero_cnj,
                    "tribunal": p.tribunal,
                    "situacao": p.situacao,
                    "score_auditoria": p.score_auditoria,
                    "ultima_movimentacao_data": str(p.ultima_movimentacao_data) if p.ultima_movimentacao_data else None,
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
    """Detalhes de um processo com partes e movimentações."""
    try:
        from src.schemas.processo_schemas import ProcessoResponse

        resultado = await session.execute(
            select(Processo)
            .options(selectinload(Processo.partes), selectinload(Processo.movimentacoes))
            .where(Processo.id == processo_id)
        )
        processo = resultado.scalar_one_or_none()

        if not processo:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        return {
            "id": processo.id,
            "numero_cnj": processo.numero_cnj,
            "tribunal": processo.tribunal,
            "grau": processo.grau,
            "vara": processo.vara,
            "comarca": processo.comarca,
            "classe_processual": processo.classe_processual,
            "assunto": processo.assunto,
            "valor_causa": float(processo.valor_causa) if processo.valor_causa else None,
            "data_distribuicao": str(processo.data_distribuicao) if processo.data_distribuicao else None,
            "situacao": processo.situacao,
            "segredo_justica": processo.segredo_justica,
            "observacoes": processo.observacoes,
            "score_auditoria": processo.score_auditoria,
            "notas_auditoria": processo.notas_auditoria,
            "ultima_movimentacao_data": str(processo.ultima_movimentacao_data) if processo.ultima_movimentacao_data else None,
            "criado_em": processo.criado_em.isoformat() if processo.criado_em else None,
            "atualizado_em": processo.atualizado_em.isoformat() if processo.atualizado_em else None,
            "partes": [
                {
                    "id": p.id,
                    "processo_id": p.processo_id,
                    "tipo_parte": p.tipo_parte,
                    "nome": p.nome,
                    "documento": p.documento,
                    "oab": p.oab,
                    "polo": p.polo,
                }
                for p in processo.partes
            ],
            "movimentacoes": [
                {
                    "id": m.id,
                    "processo_id": m.processo_id,
                    "data_movimentacao": str(m.data_movimentacao),
                    "tipo": m.tipo,
                    "descricao": m.descricao,
                    "complemento": m.complemento,
                    "codigo_nacional": m.codigo_nacional,
                    "categoria": m.categoria,
                    "impacto": m.impacto,
                }
                for m in sorted(processo.movimentacoes, key=lambda x: x.data_movimentacao, reverse=True)
            ],
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("processos.obter.failure", processo_id=processo_id)
        raise HTTPException(status_code=500, detail="Erro interno ao obter processo")


@app.post("/api/processos", tags=["processos"], response_model=dict, status_code=status.HTTP_201_CREATED)
async def criar_processo(
    req: dict,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Cria um novo processo manualmente."""
    from src.schemas.processo_schemas import ProcessoCreate
    from src.database.models import Parte, Movimentacao

    try:
        payload = ProcessoCreate(**req)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {str(e)}")

    try:
        # Verificar se CNJ já existe
        existente = await session.execute(
            select(Processo).where(Processo.numero_cnj == payload.numero_cnj)
        )
        if existente.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Processo com este CNJ já existe")

        # Criar processo
        processo = Processo(
            numero_cnj=payload.numero_cnj,
            tribunal=payload.tribunal,
            grau=payload.grau,
            vara=payload.vara,
            comarca=payload.comarca,
            classe_processual=payload.classe_processual,
            assunto=payload.assunto,
            valor_causa=payload.valor_causa,
            data_distribuicao=payload.data_distribuicao,
            situacao=payload.situacao or "Em Andamento",
            segredo_justica=payload.segredo_justica,
            observacoes=payload.observacoes,
        )
        session.add(processo)
        await session.flush()  # Para obter o ID

        # Criar partes
        for parte_data in payload.partes:
            parte = Parte(
                processo_id=processo.id,
                tipo_parte=parte_data.tipo_parte,
                nome=parte_data.nome,
                documento=parte_data.documento,
                oab=parte_data.oab,
                polo=parte_data.polo,
            )
            session.add(parte)

        # Criar movimentações
        for mov_data in payload.movimentacoes:
            mov = Movimentacao(
                processo_id=processo.id,
                data_movimentacao=mov_data.data_movimentacao,
                descricao=mov_data.descricao,
                tipo=mov_data.tipo,
                complemento=mov_data.complemento,
                codigo_nacional=mov_data.codigo_nacional,
                categoria=mov_data.categoria,
                impacto=mov_data.impacto,
            )
            session.add(mov)

        await session.commit()
        await session.refresh(processo)

        logger.info("processo.criado", processo_id=processo.id, numero_cnj=processo.numero_cnj)

        return {
            "id": processo.id,
            "numero_cnj": processo.numero_cnj,
            "tribunal": processo.tribunal,
            "status": "criado com sucesso",
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("processo.criar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao criar processo")


@app.put("/api/processos/{processo_id}", tags=["processos"])
async def atualizar_processo(
    processo_id: int,
    req: dict,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Atualiza um processo existente."""
    from src.schemas.processo_schemas import ProcessoUpdate

    try:
        payload = ProcessoUpdate(**req)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {str(e)}")

    try:
        resultado = await session.execute(
            select(Processo).where(Processo.id == processo_id)
        )
        processo = resultado.scalar_one_or_none()

        if not processo:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        # Atualizar campos fornecidos
        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(processo, field, value)

        await session.commit()
        await session.refresh(processo)

        logger.info("processo.atualizado", processo_id=processo.id)

        return {
            "id": processo.id,
            "numero_cnj": processo.numero_cnj,
            "status": "atualizado com sucesso",
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("processo.atualizar.failure", processo_id=processo_id)
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar processo")


@app.delete("/api/processos/{processo_id}", tags=["processos"])
async def deletar_processo(
    processo_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Deleta um processo e todos os dados relacionados."""
    try:
        resultado = await session.execute(
            select(Processo).where(Processo.id == processo_id)
        )
        processo = resultado.scalar_one_or_none()

        if not processo:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        numero_cnj = processo.numero_cnj
        await session.delete(processo)
        await session.commit()

        logger.info("processo.deletado", processo_id=processo_id, numero_cnj=numero_cnj)

        return {
            "status": "deletado com sucesso",
            "numero_cnj": numero_cnj,
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("processo.deletar.failure", processo_id=processo_id)
        raise HTTPException(status_code=500, detail="Erro interno ao deletar processo")


# ============================================================================
# MONITORAMENTOS
# ============================================================================

@app.get("/api/monitoramentos", tags=["monitoramentos"])
async def listar_monitoramentos(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    ativo: Optional[bool] = Query(None),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Lista monitoramentos com filtros."""
    try:
        query = select(Monitoramento).offset(skip).limit(limit)
        if ativo is not None:
            query = query.where(Monitoramento.ativo == ativo)
        query = query.order_by(Monitoramento.criado_em.desc())

        result = await session.execute(query)
        monitors = result.scalars().all()

        count_query = select(func.count(Monitoramento.id))
        if ativo is not None:
            count_query = count_query.where(Monitoramento.ativo == ativo)
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        return {
            "data": [
                {
                    "id": m.id,
                    "processo_id": m.processo_id,
                    "ativo": m.ativo,
                    "ultima_verificacao": m.ultima_verificacao.isoformat() if m.ultima_verificacao else None,
                    "proxima_verificacao": m.proxima_verificacao.isoformat() if m.proxima_verificacao else None,
                    "notificar_email": m.notificar_email,
                    "webhook_url": m.webhook_url,
                    "criado_em": m.criado_em.isoformat() if m.criado_em else None,
                }
                for m in monitors
            ],
            "total": total,
        }
    except Exception:
        logger.exception("monitoramentos.listar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao listar monitoramentos")


@app.post("/api/monitoramentos", tags=["monitoramentos"], status_code=status.HTTP_201_CREATED)
async def criar_monitoramento(
    req: dict,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Cria um novo monitoramento para um processo."""
    from src.schemas.processo_schemas import MonitoramentoCreate

    try:
        payload = MonitoramentoCreate(**req)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {str(e)}")

    try:
        # Verificar se processo existe
        proc_result = await session.execute(
            select(Processo).where(Processo.id == payload.processo_id)
        )
        if not proc_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        monitoramento = Monitoramento(
            processo_id=payload.processo_id,
            notificar_email=payload.notificar_email,
            webhook_url=payload.webhook_url,
            ativo=True,
        )
        session.add(monitoramento)
        await session.commit()
        await session.refresh(monitoramento)

        logger.info("monitoramento.criado", monitoramento_id=monitoramento.id, processo_id=payload.processo_id)

        return {
            "id": monitoramento.id,
            "processo_id": monitoramento.processo_id,
            "status": "criado com sucesso",
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("monitoramento.criar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao criar monitoramento")


@app.delete("/api/monitoramentos/{monitoramento_id}", tags=["monitoramentos"])
async def deletar_monitoramento(
    monitoramento_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Deleta um monitoramento."""
    try:
        resultado = await session.execute(
            select(Monitoramento).where(Monitoramento.id == monitoramento_id)
        )
        monitoramento = resultado.scalar_one_or_none()

        if not monitoramento:
            raise HTTPException(status_code=404, detail="Monitoramento não encontrado")

        await session.delete(monitoramento)
        await session.commit()

        logger.info("monitoramento.deletado", monitoramento_id=monitoramento_id)

        return {"status": "deletado com sucesso"}

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("monitoramento.deletar.failure", monitoramento_id=monitoramento_id)
        raise HTTPException(status_code=500, detail="Erro interno ao deletar monitoramento")


@app.patch("/api/monitoramentos/{monitoramento_id}/ativar", tags=["monitoramentos"])
async def ativar_monitoramento(
    monitoramento_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Ativa ou desativa um monitoramento."""
    try:
        resultado = await session.execute(
            select(Monitoramento).where(Monitoramento.id == monitoramento_id)
        )
        monitoramento = resultado.scalar_one_or_none()

        if not monitoramento:
            raise HTTPException(status_code=404, detail="Monitoramento não encontrado")

        monitoramento.ativo = not monitoramento.ativo
        await session.commit()

        logger.info("monitoramento.toggled", monitoramento_id=monitoramento_id, ativo=monitoramento.ativo)

        return {
            "id": monitoramento.id,
            "ativo": monitoramento.ativo,
            "status": "atualizado",
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("monitoramento.toggle.failure", monitoramento_id=monitoramento_id)
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar monitoramento")


# ============================================================================
# PRAZOS
# ============================================================================

@app.get("/api/prazos", tags=["prazos"])
async def listar_prazos(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    cumprido: Optional[bool] = Query(None),
    processo_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Lista prazos com filtros."""
    try:
        query = select(Prazo).offset(skip).limit(limit)
        if cumprido is not None:
            query = query.where(Prazo.cumprido == cumprido)
        if processo_id is not None:
            query = query.where(Prazo.processo_id == processo_id)
        query = query.order_by(Prazo.data_vencimento)

        result = await session.execute(query)
        prazos = result.scalars().all()

        count_query = select(func.count(Prazo.id))
        if cumprido is not None:
            count_query = count_query.where(Prazo.cumprido == cumprido)
        if processo_id is not None:
            count_query = count_query.where(Prazo.processo_id == processo_id)
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        return {
            "data": [
                {
                    "id": p.id,
                    "processo_id": p.processo_id,
                    "tipo_prazo": p.tipo_prazo,
                    "descricao": p.descricao,
                    "data_inicio": str(p.data_inicio),
                    "data_vencimento": str(p.data_vencimento),
                    "dias_uteis": p.dias_uteis,
                    "cumprido": p.cumprido,
                    "observacao": p.observacao,
                    "criado_em": p.criado_em.isoformat() if p.criado_em else None,
                }
                for p in prazos
            ],
            "total": total,
        }
    except Exception:
        logger.exception("prazos.listar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao listar prazos")


@app.post("/api/prazos", tags=["prazos"], status_code=status.HTTP_201_CREATED)
async def criar_prazo(
    req: dict,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Cria um novo prazo para um processo."""
    from src.schemas.processo_schemas import PrazoCreate

    try:
        payload = PrazoCreate(**req)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {str(e)}")

    try:
        # Verificar se processo existe
        proc_result = await session.execute(
            select(Processo).where(Processo.id == payload.processo_id)
        )
        if not proc_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        prazo = Prazo(
            processo_id=payload.processo_id,
            tipo_prazo=payload.tipo_prazo,
            descricao=payload.descricao,
            data_inicio=payload.data_inicio,
            data_vencimento=payload.data_vencimento,
            dias_uteis=payload.dias_uteis,
            cumprido=payload.cumprido,
            observacao=payload.observacao,
        )
        session.add(prazo)
        await session.commit()
        await session.refresh(prazo)

        logger.info("prazo.criado", prazo_id=prazo.id, processo_id=payload.processo_id)

        return {
            "id": prazo.id,
            "processo_id": prazo.processo_id,
            "status": "criado com sucesso",
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("prazo.criar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao criar prazo")


@app.put("/api/prazos/{prazo_id}", tags=["prazos"])
async def atualizar_prazo(
    prazo_id: int,
    req: dict,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Atualiza um prazo existente."""
    from src.schemas.processo_schemas import PrazoUpdate

    try:
        payload = PrazoUpdate(**req)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Dados inválidos: {str(e)}")

    try:
        resultado = await session.execute(
            select(Prazo).where(Prazo.id == prazo_id)
        )
        prazo = resultado.scalar_one_or_none()

        if not prazo:
            raise HTTPException(status_code=404, detail="Prazo não encontrado")

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(prazo, field, value)

        await session.commit()
        await session.refresh(prazo)

        logger.info("prazo.atualizado", prazo_id=prazo.id)

        return {
            "id": prazo.id,
            "status": "atualizado com sucesso",
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("prazo.atualizar.failure", prazo_id=prazo_id)
        raise HTTPException(status_code=500, detail="Erro interno ao atualizar prazo")


@app.delete("/api/prazos/{prazo_id}", tags=["prazos"])
async def deletar_prazo(
    prazo_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Deleta um prazo."""
    try:
        resultado = await session.execute(
            select(Prazo).where(Prazo.id == prazo_id)
        )
        prazo = resultado.scalar_one_or_none()

        if not prazo:
            raise HTTPException(status_code=404, detail="Prazo não encontrado")

        await session.delete(prazo)
        await session.commit()

        logger.info("prazo.deletado", prazo_id=prazo_id)

        return {"status": "deletado com sucesso"}

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("prazo.deletar.failure", prazo_id=prazo_id)
        raise HTTPException(status_code=500, detail="Erro interno ao deletar prazo")


@app.patch("/api/prazos/{prazo_id}/cumprir", tags=["prazos"])
async def cumprir_prazo(
    prazo_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Marca um prazo como cumprido."""
    try:
        resultado = await session.execute(
            select(Prazo).where(Prazo.id == prazo_id)
        )
        prazo = resultado.scalar_one_or_none()

        if not prazo:
            raise HTTPException(status_code=404, detail="Prazo não encontrado")

        prazo.cumprido = True
        await session.commit()

        logger.info("prazo.cumprido", prazo_id=prazo_id)

        return {
            "id": prazo.id,
            "cumprido": prazo.cumprido,
            "status": "marcado como cumprido",
        }

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("prazo.cumprir.failure", prazo_id=prazo_id)
        raise HTTPException(status_code=500, detail="Erro interno ao cumprir prazo")


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


@app.patch("/api/notificacoes/{notificacao_id}/lida", tags=["notificacoes"])
async def marcar_notificacao_lida(
    notificacao_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Marca uma notificação como lida."""
    try:
        resultado = await session.execute(
            select(Notificacao).where(Notificacao.id == notificacao_id)
        )
        notificacao = resultado.scalar_one_or_none()

        if not notificacao:
            raise HTTPException(status_code=404, detail="Notificação não encontrada")

        notificacao.lida = True
        await session.commit()

        logger.info("notificacao.marcada_lida", notificacao_id=notificacao_id)

        return {"id": notificacao.id, "lida": True, "status": "marcada como lida"}

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("notificacao.marcar_lida.failure", notificacao_id=notificacao_id)
        raise HTTPException(status_code=500, detail="Erro interno ao marcar notificação")


@app.post("/api/notificacoes/marcar_todas_lidas", tags=["notificacoes"])
async def marcar_todas_notificacoes_lidas(
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Marca todas as notificações como lidas."""
    try:
        result = await session.execute(
            select(Notificacao).where(Notificacao.lida == False)
        )
        notificacoes = result.scalars().all()

        for n in notificacoes:
            n.lida = True

        await session.commit()

        logger.info("notificacoes.marcadas_lidas", total=len(notificacoes))

        return {"status": "ok", "total_marcadas": len(notificacoes)}

    except Exception:
        await session.rollback()
        logger.exception("notificacoes.marcar_todas_lidas.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao marcar notificações")


@app.delete("/api/notificacoes/{notificacao_id}", tags=["notificacoes"])
async def deletar_notificacao(
    notificacao_id: int,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Deleta uma notificação."""
    try:
        resultado = await session.execute(
            select(Notificacao).where(Notificacao.id == notificacao_id)
        )
        notificacao = resultado.scalar_one_or_none()

        if not notificacao:
            raise HTTPException(status_code=404, detail="Notificação não encontrada")

        await session.delete(notificacao)
        await session.commit()

        logger.info("notificacao.deletada", notificacao_id=notificacao_id)

        return {"status": "deletada com sucesso"}

    except HTTPException:
        raise
    except Exception:
        await session.rollback()
        logger.exception("notificacao.deletar.failure", notificacao_id=notificacao_id)
        raise HTTPException(status_code=500, detail="Erro interno ao deletar notificação")


# ============================================================================
# ADVOGADOS
# ============================================================================

@app.get("/api/advogados", tags=["advogados"])
async def buscar_advogados(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    nome: Optional[str] = Query(None),
    numero_oab: Optional[str] = Query(None),
    uf: Optional[str] = Query(None),
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Busca advogados no catálogo global."""
    try:
        from src.database.models import AdvogadoCatalog

        query = select(AdvogadoCatalog)
        count_query = select(func.count(AdvogadoCatalog.id))

        if nome:
            query = query.where(AdvogadoCatalog.nome_completo.ilike(f"%{nome}%"))
            count_query = count_query.where(AdvogadoCatalog.nome_completo.ilike(f"%{nome}%"))
        if numero_oab:
            query = query.where(AdvogadoCatalog.numero_oab.ilike(f"%{numero_oab}%"))
            count_query = count_query.where(AdvogadoCatalog.numero_oab.ilike(f"%{numero_oab}%"))
        if uf:
            query = query.where(AdvogadoCatalog.uf == uf.upper())
            count_query = count_query.where(AdvogadoCatalog.uf == uf.upper())

        query = query.order_by(AdvogadoCatalog.total_processos_encontrados.desc()).offset(skip).limit(limit)
        result = await session.execute(query)
        advogados = result.scalars().all()

        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0

        return {
            "data": [
                {
                    "id": a.id,
                    "numero_oab": a.numero_oab,
                    "uf": a.uf,
                    "nome_completo": a.nome_completo,
                    "cpf": a.cpf,
                    "total_processos": a.total_processos_encontrados,
                    "ultima_consulta_at": a.ultima_consulta_at.isoformat() if a.ultima_consulta_at else None,
                }
                for a in advogados
            ],
            "total": total,
        }
    except Exception:
        logger.exception("advogados.buscar.failure")
        raise HTTPException(status_code=500, detail="Erro interno ao buscar advogados")


@app.get("/api/advogados/{numero_oab}/{uf}", tags=["advogados"])
async def obter_advogado(
    numero_oab: str,
    uf: str,
    session: AsyncSession = Depends(AsyncSessionLocal),
):
    """Detalhes de um advogado específico pelo número OAB e UF."""
    try:
        from src.database.models import AdvogadoCatalog

        resultado = await session.execute(
            select(AdvogadoCatalog).where(
                and_(
                    AdvogadoCatalog.numero_oab == numero_oab,
                    AdvogadoCatalog.uf == uf.upper()
                )
            )
        )
        advogado = resultado.scalar_one_or_none()

        if not advogado:
            raise HTTPException(status_code=404, detail="Advogado não encontrado no catálogo")

        return {
            "id": advogado.id,
            "numero_oab": advogado.numero_oab,
            "uf": advogado.uf,
            "nome_completo": advogado.nome_completo,
            "cpf": advogado.cpf,
            "total_processos": advogado.total_processos_encontrados,
            "ultima_consulta_at": advogado.ultima_consulta_at.isoformat() if advogado.ultima_consulta_at else None,
            "criado_em": advogado.criado_em.isoformat() if advogado.criado_em else None,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("advogado.obter.failure", numero_oab=numero_oab, uf=uf)
        raise HTTPException(status_code=500, detail="Erro interno ao obter advogado")


# ============================================================================
# BUSCA POR OAB
# ============================================================================

class BuscaOABRequest(BaseModel):
    numero_oab: str
    uf_oab: str
    tribunais: Optional[list[str]] = None
    salvar_bd: bool = True


@app.post("/api/buscar/oab", tags=["busca"])
@limiter.limit("10/minute")
async def buscar_por_oab(
    req: BuscaOABRequest,
    session: AsyncSession = Depends(AsyncSessionLocal),
    current_user: dict = Depends(get_current_user),
):
    """
    Busca processos por número de OAB em todos os tribunais disponíveis
    e opcionalmente persiste os resultados no banco de dados.

    ⚠️ Requer autenticação (JWT Bearer token).
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
                    "assunto": p.assunto,
                    "situacao": p.situacao,
                    "valor_causa": float(p.valor_causa) if p.valor_causa else None,
                    "data_distribuicao": str(p.data_distribuicao) if p.data_distribuicao else None,
                    "score_auditoria": p.score_auditoria,
                    "notas_auditoria": p.notas_auditoria or [],
                    "segredo_justica": p.segredo_justica,
                    "partes": [
                        {
                            "nome": parte.nome,
                            "tipo": parte.tipo_parte,
                            "polo": parte.polo,
                            "documento": parte.documento,
                            "oab": parte.oab,
                        }
                        for parte in p.partes
                    ],
                    "movimentacoes": [
                        {
                            "data": str(m.data_movimentacao),
                            "descricao": m.descricao,
                            "tipo": m.tipo,
                            "categoria": m.categoria,
                            "impacto": m.impacto,
                        }
                        for m in p.movimentacoes
                    ],
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
@limiter.limit("30/minute")
async def buscar_por_cnj(
    numero_cnj: str,
    tribunal: Optional[str] = Query(None),
    session: AsyncSession = Depends(AsyncSessionLocal),
    current_user: dict = Depends(get_current_user),
):
    """
    Busca um processo específico pelo número CNJ via DataJud.

    ⚠️ Requer autenticação (JWT Bearer token).
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
            "grau": proc.grau,
            "vara": proc.vara,
            "comarca": proc.comarca,
            "classe_processual": proc.classe_processual,
            "assunto": proc.assunto,
            "situacao": proc.situacao,
            "valor_causa": float(proc.valor_causa) if proc.valor_causa else None,
            "data_distribuicao": str(proc.data_distribuicao) if proc.data_distribuicao else None,
            "score_auditoria": proc.score_auditoria,
            "notas_auditoria": proc.notas_auditoria or [],
            "segredo_justica": proc.segredo_justica,
            "partes": [
                {
                    "nome": p.nome,
                    "tipo": p.tipo_parte,
                    "polo": p.polo,
                    "documento": p.documento,
                    "oab": p.oab,
                }
                for p in proc.partes
            ],
            "movimentacoes": [
                {
                    "data": str(m.data_movimentacao),
                    "descricao": m.descricao,
                    "tipo": m.tipo,
                    "categoria": m.categoria,
                    "impacto": m.impacto,
                }
                for m in proc.movimentacoes
            ],
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
# DASHBOARD SPA
# ============================================================================

import os
import pathlib

_dashboard_path = pathlib.Path(__file__).parent.parent / "dashboard" / "public"


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """
    Dashboard SPA — interface web completa para o sistema jurídico.

    O dashboard em dashboard/public/index.html consome a própria API REST
    (configurável na barra lateral). Ele substitui completamente o HTML
    hardcoded anterior.
    """
    index_path = _dashboard_path / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"), status_code=200)
    # Fallback: se o dashboard não estiver implantado
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"><title>JurídicoCrawler API</title></head>
<body style="font-family:sans-serif;background:#0a1628;color:#e2e8f0;display:flex;align-items:center;
justify-content:center;height:100vh;margin:0;">
<div style="text-align:center">
  <h1 style="color:#818cf8">⚖️ JurídicoCrawler API</h1>
  <p>API no ar! Acesse <a href="/docs" style="color:#a5b4fc">Swagger UI</a> para testar os endpoints.</p>
</div></body></html>""", status_code=200)
