"""
Jobs do APScheduler para atualização automática de processos monitorados.
"""

import structlog
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.config import settings
from src.crawlers.datajud import DataJudCrawler
from src.database.connection import AsyncSessionLocal
from src.database.models import Monitoramento, Movimentacao, Notificacao, Parte, Processo

logger = structlog.get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Callbacks de notificação registrados em runtime
_notification_callbacks: list = []


def registrar_callback_notificacao(callback) -> None:
    """Registra um callback para ser chamado quando novas movimentações são detectadas."""
    _notification_callbacks.append(callback)


async def _notificar_novas_movimentacoes(
    db,
    processo: Processo,
    novas_movs: list,
    email: str | None = None,
    webhook_url: str | None = None,
) -> None:
    """Persiste notificação no banco, dispara webhook e callbacks."""
    if not novas_movs:
        return

    resumo_movs = "; ".join(
        f"{m.data_movimentacao}: {m.descricao[:80]}" for m in novas_movs[:5]
    )
    payload = {
        "tipo": "NOVA_MOVIMENTACAO",
        "processo_id": processo.id,
        "numero_cnj": processo.numero_cnj,
        "tribunal": processo.tribunal,
        "total_novas": len(novas_movs),
        "movimentacoes": [
            {
                "data": str(m.data_movimentacao),
                "descricao": m.descricao,
                "categoria": m.categoria,
                "impacto": m.impacto,
            }
            for m in novas_movs
        ],
        "notificar_email": email,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Persistir notificação no banco
    db.add(Notificacao(
        processo_id=processo.id,
        tipo="NOVA_MOVIMENTACAO",
        resumo=f"{len(novas_movs)} nova(s) movimentação(ões): {resumo_movs}",
        dados=payload,
    ))

    logger.info(
        "ALERTA: %d nova(s) movimentação(ões) no processo %s: %s",
        len(novas_movs),
        processo.numero_cnj,
        resumo_movs[:120],
    )

    # Disparar webhook se configurado
    if webhook_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(webhook_url, json=payload)
                logger.info("Webhook %s: status %d", webhook_url, resp.status_code)
        except Exception as e:
            logger.warning("Webhook falhou para %s: %s", webhook_url, e)

    # Callbacks em memória
    for callback in _notification_callbacks:
        try:
            import asyncio
            if asyncio.iscoroutinefunction(callback):
                await callback(payload)
            else:
                callback(payload)
        except Exception as e:
            logger.error("Erro no callback de notificação: %s", e)


async def _merge_movimentacoes(
    db, processo_id: int, novas_movs: list,
) -> list[Movimentacao]:
    """
    Smart merge de movimentações: insere apenas as que não existem.
    Retorna a lista de movimentações efetivamente adicionadas.
    """
    if not novas_movs:
        return []

    stmt = select(Movimentacao).where(Movimentacao.processo_id == processo_id)
    result = await db.execute(stmt)
    existentes = result.scalars().all()

    chaves_vistas = {
        (m.data_movimentacao, (m.descricao or "")[:100].strip())
        for m in existentes
    }

    adicionadas = []
    for m in novas_movs:
        chave = (m.data_movimentacao, (m.descricao or "")[:100].strip())
        if chave not in chaves_vistas:
            mov_db = Movimentacao(
                processo_id=processo_id,
                data_movimentacao=m.data_movimentacao,
                tipo=m.tipo,
                descricao=m.descricao,
                complemento=m.complemento,
                codigo_nacional=m.codigo_nacional,
                categoria=m.categoria,
                impacto=m.impacto,
            )
            db.add(mov_db)
            chaves_vistas.add(chave)
            adicionadas.append(mov_db)

    return adicionadas


async def _merge_partes(db, processo_id: int, novas_partes: list) -> None:
    """Smart merge de partes: substitui somente se vieram dados novos."""
    if not novas_partes:
        return

    await db.execute(
        Parte.__table__.delete().where(Parte.processo_id == processo_id)
    )
    for p in novas_partes:
        db.add(Parte(
            processo_id=processo_id,
            tipo_parte=(p.tipo_parte or "")[:50],
            nome=(p.nome or "")[:300],
            documento=(p.documento or None) and p.documento[:20],
            oab=(p.oab or None) and p.oab[:20],
            polo=(p.polo or None) and p.polo[:10],
        ))


async def atualizar_processos_monitorados() -> None:
    """
    Job principal: atualiza todos os processos com monitoramento ativo
    que já passaram da proxima_verificacao.
    Agora faz merge inteligente de partes e movimentações e notifica novas.
    """
    logger.info("Iniciando atualização de processos monitorados...")
    agora = datetime.utcnow()
    atualizados = 0
    erros = 0

    async with AsyncSessionLocal() as db:
        stmt = (
            select(Monitoramento)
            .options(selectinload(Monitoramento.processo))
            .where(
                Monitoramento.ativo == True,
                Monitoramento.proxima_verificacao <= agora,
            )
        )
        result = await db.execute(stmt)
        monitoramentos = result.scalars().all()

        logger.info("Processos a atualizar: %d", len(monitoramentos))

        async with DataJudCrawler() as crawler:
            for mon in monitoramentos:
                processo = mon.processo
                try:
                    logger.debug("Atualizando processo %s", processo.numero_cnj)
                    processo_novo = await crawler.buscar_processo(
                        numero_cnj=processo.numero_cnj,
                        tribunal=processo.tribunal,
                        usar_ai_parser=False,
                    )

                    if processo_novo:
                        # Atualizar campos básicos
                        processo.vara = processo_novo.vara or processo.vara
                        processo.comarca = processo_novo.comarca or processo.comarca
                        processo.classe_processual = processo_novo.classe_processual or processo.classe_processual
                        processo.assunto = processo_novo.assunto or processo.assunto
                        processo.valor_causa = processo_novo.valor_causa or processo.valor_causa
                        processo.data_distribuicao = processo_novo.data_distribuicao or processo.data_distribuicao
                        processo.situacao = processo_novo.situacao or processo.situacao
                        processo.segredo_justica = processo_novo.segredo_justica
                        processo.dados_brutos = processo_novo.dados_brutos

                        # Merge inteligente de partes
                        await _merge_partes(db, processo.id, processo_novo.partes)

                        # Merge inteligente de movimentações + detecção de novas
                        novas_movs = await _merge_movimentacoes(
                            db, processo.id, processo_novo.movimentacoes,
                        )

                        # Atualizar campo desnormalizado
                        if processo_novo.movimentacoes:
                            mais_recente = max(m.data_movimentacao for m in processo_novo.movimentacoes)
                            processo.ultima_movimentacao_data = mais_recente

                        # Notificar se há novas movimentações
                        if novas_movs:
                            await _notificar_novas_movimentacoes(
                                db, processo, novas_movs,
                                mon.notificar_email, mon.webhook_url,
                            )

                    mon.ultima_verificacao = agora
                    mon.proxima_verificacao = agora + timedelta(hours=24)
                    atualizados += 1

                except Exception as e:
                    logger.error(
                        "Erro ao atualizar processo %s: %s",
                        processo.numero_cnj,
                        e,
                    )
                    erros += 1
                    mon.proxima_verificacao = agora + timedelta(hours=6)

        await db.commit()

    logger.info(
        "Atualização concluída: %d processos atualizados, %d erros",
        atualizados,
        erros,
    )


def criar_scheduler() -> AsyncIOScheduler:
    """Cria e configura o scheduler com os jobs registrados."""
    global _scheduler

    scheduler = AsyncIOScheduler(timezone="America/Sao_Paulo")

    # Job principal: atualização diária no horário configurado
    scheduler.add_job(
        atualizar_processos_monitorados,
        trigger=CronTrigger(
            hour=settings.scheduler_cron_hora,
            minute=settings.scheduler_cron_minuto,
            timezone="America/Sao_Paulo",
        ),
        id="atualizar_processos",
        name="Atualização diária de processos monitorados",
        replace_existing=True,
        misfire_grace_time=3600,  # Tolerância de 1 hora para atrasos
    )

    _scheduler = scheduler
    return scheduler


def obter_scheduler() -> AsyncIOScheduler | None:
    return _scheduler
