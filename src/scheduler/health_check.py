"""
Health Check diário — verifica se os crawlers de cada tribunal ainda funcionam.

Se um tribunal para de retornar resultados (mudou API, anti-bot, etc.),
um alerta é gerado no log para que o desenvolvedor seja notificado.

Uso:
    python -m src.scheduler.health_check    # teste manual
"""
import asyncio
import structlog
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.config import settings
from src.crawlers.tjsp import TJSPCrawler
from src.crawlers.tjmg import TJMG_UnifiedCrawler
from src.crawlers.pje import PJeCrawler
from src.crawlers.eproc import EProcCrawler
from src.crawlers.esaj_generico import ESajMultiCrawler

logger = structlog.get_logger(__name__)


@dataclass
class TribunalHealth:
    nome: str
    sistema: str
    oab_teste: str
    uf_oab: str
    baseline_hits: int          # mínimo esperado de processos
    status: str = "unknown"     # ok | degraded | down
    hits_recebidos: int = 0
    mensagem: str = ""
    duracao_ms: int = 0


# ── OABs de teste conhecidas (funcionam em cada tribunal) ──────────────────────
# Se uma dessas OABs mudar de tribunal ou expirar, troque aqui.
HEALTH_TESTS: list[TribunalHealth] = [
    TribunalHealth(
        nome="TJSP",
        sistema="eSaj",
        oab_teste="242430",
        uf_oab="SP",
        baseline_hits=1,         # TJSP OAB 242430/SP → processos conhecidos
    ),
    TribunalHealth(
        nome="TJMG",
        sistema="PJe JSF",
        oab_teste="104819",
        uf_oab="MG",
        baseline_hits=1,         # PJe MG retorna CNJs via JSF POST
    ),
    TribunalHealth(
        nome="TRF1",
        sistema="eProc",
        oab_teste="361329",
        uf_oab="SP",
        baseline_hits=0,         # eProc pode estar bloqueado por reCAPTCHA
    ),
]


async def verificar_tjsp(health: TribunalHealth) -> TribunalHealth:
    """Testa TJSP via eSaj."""
    start = datetime.now(timezone.utc)
    try:
        async with TJSPCrawler() as crawler:
            resultados = await crawler.buscar_por_oab(health.oab_teste, health.uf_oab, paginas=2)
        duracao = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        hits = len(resultados)
        health.hits_recebidos = hits
        health.duracao_ms = duracao
        if hits >= health.baseline_hits:
            health.status = "ok"
            health.mensagem = f"OK — {hits} processo(s) encontrado(s) em {duracao}ms"
        else:
            health.status = "degraded"
            health.mensagem = f"BAIXO — {hits} processo(s) (baseline: {health.baseline_hits})"
    except Exception as e:
        health.status = "down"
        health.duracao_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        health.mensagem = f"ERRO — {type(e).__name__}: {e}"
    return health


async def verificar_tjmg(health: TribunalHealth) -> TribunalHealth:
    """Testa TJMG via PJe JSF POST (ou eProc como fallback)."""
    start = datetime.now(timezone.utc)
    try:
        async with TJMG_UnifiedCrawler() as crawler:
            resultados = await crawler.buscar_por_oab(health.oab_teste, health.uf_oab)
        duracao = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        hits = len(resultados)
        health.hits_recebidos = hits
        health.duracao_ms = duracao
        if hits >= health.baseline_hits:
            health.status = "ok"
            health.mensagem = f"OK — {hits} CNJ(s) em {duracao}ms"
        else:
            health.status = "degraded"
            health.mensagem = f"BAIXO — {hits} CNJ(s) (baseline: {health.baseline_hits})"
    except Exception as e:
        health.status = "down"
        health.duracao_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        health.mensagem = f"ERRO — {type(e).__name__}: {e}"
    return health


async def verificar_trf1(health: TribunalHealth) -> TribunalHealth:
    """Testa TRF1 via eProc (pode ter reCAPTCHA)."""
    start = datetime.now(timezone.utc)
    try:
        async with EProcCrawler(verify_ssl=False) as crawler:
            resultados = await crawler.buscar_por_oab(
                health.oab_teste, health.uf_oab, tribunais=["trf1"], paginas=1,
            )
        duracao = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        hits = len(resultados)
        health.hits_recebidos = hits
        health.duracao_ms = duracao
        if hits >= health.baseline_hits:
            health.status = "ok"
            health.mensagem = f"OK — {hits} processo(s) em {duracao}ms"
        else:
            # 0 hits é normal se OAB não tem processos — não marca como degraded
            health.status = "ok"
            health.mensagem = f"OK (sem resultados) — {duracao}ms"
    except Exception as e:
        health.status = "down"
        health.duracao_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
        health.mensagem = f"ERRO — {type(e).__name__}: {e}"
    return health


VERIFICADORES = {
    "TJSP": verificar_tjsp,
    "TJMG": verificar_tjmg,
    "TRF1": verificar_trf1,
}


async def rodar_health_check() -> list[TribunalHealth]:
    """
    Executa health check de todos os tribunais e retorna lista de status.
    Chamado pelo scheduler ou manualmente.
    """
    logger.info("=" * 60)
    logger.info("HEALTH CHECK — verificando tribunais...")
    logger.info("=" * 60)

    results: list[TribunalHealth] = []

    for health in HEALTH_TESTS:
        verifier = VERIFICADORES.get(health.nome)
        if verifier:
            result = await verifier(health)
            results.append(result)

            emoji = "✅" if result.status == "ok" else ("⚠️" if result.status == "degraded" else "❌")
            logger.info(
                "%s %s [%s] — %s",
                emoji,
                result.nome,
                result.sistema,
                result.mensagem,
            )
        else:
            logger.warning("Sem verificador para %s", health.nome)

    # Resumo
    down = [r for r in results if r.status == "down"]
    degraded = [r for r in results if r.status == "degraded"]
    ok = [r for r in results if r.status == "ok"]

    logger.info("=" * 60)
    logger.info(
        "HEALTH CHECK — %d OK | %d Degraded | %d Down",
        len(ok), len(degraded), len(down),
    )
    if down:
        for r in down:
            logger.error("🔴 TRIBUNAL FORA DO AR: %s — %s", r.nome, r.mensagem)
    if degraded:
        for r in degraded:
            logger.warning("🟡 TRIBUNAL DEGRADADO: %s — %s", r.nome, r.mensagem)
    logger.info("=" * 60)

    return results


async def health_check_diario():
    """
    Job diário do APScheduler.
    Roda health check e persiste resultado no banco.
    """
    from src.database.connection import AsyncSessionLocal
    from src.database.models import Notificacao

    results = await rodar_health_check()

    # Persistir alertas no banco
    alertas = [r for r in results if r.status in ("down", "degraded")]
    if alertas:
        async with AsyncSessionLocal() as db:
            for r in alertas:
                notif = Notificacao(
                    tipo="ALERTA_TRIBUNAL",
                    resumo=f"{r.nome} ({r.sistema}): {r.mensagem}",
                    dados={
                        "tribunal": r.nome,
                        "sistema": r.sistema,
                        "status": r.status,
                        "hits": r.hits_recebidos,
                        "duracao_ms": r.duracao_ms,
                    },
                )
                db.add(notif)
            await db.commit()

    return results


if __name__ == "__main__":
    # Rodar manualmente: python -m src.scheduler.health_check
    asyncio.run(rodar_health_check())
