"""
Crawler eSaj genérico — cobre TJs que usam a interface eSaj mas não estão
no PJe nem no eProc.

Reutiliza toda a lógica de parse do TJSPCrawler (que é o eSaj de referência)
alterando apenas a base URL e o identificador do tribunal.

Tribunais cobertos:
- TJAP, TJES, TJGO, TJMG, TJMS, TJMT, TJPA, TJPB, TJPR, TJRJ, TJRR, TJRS, TJSC, TJTO
"""

import asyncio
import structlog
from typing import Optional

from src.crawlers.tjsp import TJSPCrawler
from src.parsers.estruturas import ProcessoCompleto

logger = structlog.get_logger(__name__)

# TJs com interface eSaj, excluindo TJSP (coberto pelo TJSPCrawler) e os
# cobertos pelo PJe (TJBA, TJPE, TJCE, TJRN, TJMA, TJPI, TJAL, TJSE, TJAM, TJRO, TJAC).
# Apenas tribunais com eSAJ acessível externamente (testados em abr/2026).
# TJs que migraram para PJe/eProc ou cujo eSAJ não resolve DNS foram removidos.
ESAJ_TRIBUNAIS: dict[str, str] = {
    "tjms": "esaj.tjms.jus.br",
    # Abaixo: domínios que frequentemente ficam inacessíveis (Rede JUS interna
    # ou migração para PJe/eProc). Descomentados sob demanda.
    # "tjap": "esaj.tjap.jus.br",     # DNS não resolve (abr/2026)
    # "tjes": "esaj.tjes.jus.br",     # Migrou para PJe (pje.tjes.jus.br)
    # "tjgo": "esaj.tjgo.jus.br",     # Migrou para Projudi (projudi.tjgo.jus.br)
    # "tjmg": "sistemas.tjmg.jus.br", # DNS não resolve (abr/2026), usar PJe/eProc
    # "tjmt": "esaj.tjmt.jus.br",     # Migrou para PJe (pje.tjmt.jus.br)
    # "tjpa": "esaj.tjpa.jus.br",     # DNS não resolve (abr/2026)
    # "tjpb": "esaj.tjpb.jus.br",     # Migrou para PJe (pje.tjpb.jus.br)
    # "tjpr": "esaj.tjpr.jus.br",     # Migrou para Projudi (projudi.tjpr.jus.br)
    # "tjrj": "esaj4.tjrj.jus.br",    # DNS não resolve (abr/2026)
    # "tjrr": "esaj.tjrr.jus.br",     # DNS não resolve (abr/2026)
    # "tjrs": "esaj.tjrs.jus.br",     # Migrou para eProc (eproc1g.tjrs.jus.br, 403)
    # "tjsc": "esaj.tjsc.jus.br",     # Migrou para eProc (eproc1g.tjsc.jus.br, SSO)
    # "tjto": "esaj.tjto.jus.br",     # DNS não resolve (abr/2026)
}


class ESajGenericoCrawler(TJSPCrawler):
    """
    Crawler eSaj para qualquer tribunal da lista ESAJ_TRIBUNAIS.

    Herda 100% da lógica do TJSPCrawler — apenas muda base URL e tribunal_id.
    """

    def __init__(self, tribunal: str, **kwargs) -> None:
        if tribunal not in ESAJ_TRIBUNAIS:
            raise ValueError(
                f"Tribunal '{tribunal}' não suportado. Opções: {sorted(ESAJ_TRIBUNAIS)}"
            )
        super().__init__(
            esaj_base=f"https://{ESAJ_TRIBUNAIS[tribunal]}",
            tribunal_id=tribunal,
            **kwargs,
        )


class ESajMultiCrawler:
    """
    Busca OAB em múltiplos TJs eSaj em paralelo (máx 5 simultâneos).

    Exemplo (com proxy só para os outros TJs):
        from src.crawlers.base import ProxyPool
        proxy = ProxyPool.from_env()
        async with ESajMultiCrawler(proxy_pool=proxy) as c:
            processos = await c.buscar_por_oab("361329", "SP")
    """

    def __init__(self, proxy_pool=None) -> None:
        # proxy_pool=None            → sem proxy (usa conexão direta)
        # proxy_pool=ProxyPool([])   → sem proxy explícito
        # proxy_pool=ProxyPool.from_env() → com proxy do .env
        self._proxy_pool = proxy_pool

    async def __aenter__(self) -> "ESajMultiCrawler":
        return self

    async def __aexit__(self, *_) -> None:
        pass

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        tribunais: Optional[list[str]] = None,
        paginas: int = 3,
    ) -> list[ProcessoCompleto]:
        """
        Busca por OAB em todos (ou um subconjunto) dos TJs eSaj.

        Args:
            numero_oab: Número de inscrição na OAB (sem UF).
            uf_oab: UF da seccional OAB.
            tribunais: Lista de IDs de tribunais (ex: ["tjrj", "tjpr"]).
                       None = todos os ESAJ_TRIBUNAIS.
            paginas: Páginas a percorrer em cada tribunal (25 proc/pág).

        Returns:
            Lista plana de ProcessoCompleto de todos os tribunais.
        """
        alvos = tribunais or list(ESAJ_TRIBUNAIS.keys())
        # Filtrar apenas tribunais da lista suportada
        alvos = [t for t in alvos if t in ESAJ_TRIBUNAIS]

        if not alvos:
            return []

        semaforo = asyncio.Semaphore(5)

        async def buscar_tribunal(tribunal: str) -> list[ProcessoCompleto]:
            async with semaforo:
                # Tenta com proxy (se configurado).
                # verify_ssl=False porque proxies residenciais fazem MITM SSL.
                if self._proxy_pool and self._proxy_pool.proxies:
                    try:
                        async with ESajGenericoCrawler(
                            tribunal, proxy_pool=self._proxy_pool, verify_ssl=False
                        ) as crawler:
                            return await crawler.buscar_por_oab(
                                numero_oab=numero_oab,
                                uf_oab=uf_oab,
                                paginas=paginas,
                            )
                    except Exception as e:
                        err_str = str(e)
                        if "402" in err_str or "bad_endpoint" in err_str:
                            logger.debug(
                                "eSaj %s: proxy bloqueou (402) — tentando sem proxy",
                                tribunal.upper(),
                            )
                        else:
                            logger.debug(
                                "eSaj %s: proxy falhou (%s: %s) — tentando sem proxy",
                                tribunal.upper(), type(e).__name__, e,
                            )

                # Conexão direta (sem proxy).
                # verify_ssl=False: TJs estaduais frequentemente usam certificados
                # emitidos pela ICP-Brasil (AC Raiz v1/v2) que não estão na cadeia
                # padrão do Python/httpx — sem isso ocorre ConnectError por falha SSL.
                try:
                    async with ESajGenericoCrawler(tribunal, verify_ssl=False) as crawler:
                        return await crawler.buscar_por_oab(
                            numero_oab=numero_oab,
                            uf_oab=uf_oab,
                            paginas=paginas,
                        )
                except Exception as e:
                    logger.debug(
                        "eSaj %s: conexão direta falhou (%s: %s)",
                        tribunal.upper(), type(e).__name__, e,
                    )
                    return []

        resultados = await asyncio.gather(*[buscar_tribunal(t) for t in alvos])

        processos: list[ProcessoCompleto] = []
        for lista in resultados:
            processos.extend(lista)

        logger.info(
            "ESajMulti OAB %s/%s: %d processo(s) em %d tribunal(is)",
            numero_oab, uf_oab, len(processos), len(alvos),
        )
        return processos
