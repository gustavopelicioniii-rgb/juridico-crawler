"""
Crawler Unificado TJMG (Tribunal de Justiça de Minas Gerais).

Este crawler orquestra a busca nos três sistemas públicos do TJMG:
1. PJe via JSF POST (formulário RichFaces) — funciona para OABs reais
2. eProc (sistema atual) — tem reCAPTCHA ativo (bloqueado)
3. PJe API REST — endpoint mudou/indisponível

A prioridade é o JSF POST que funciona sem CAPTCHA nem API.
"""
import asyncio
import structlog
from typing import Optional, Any
from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import ProcessoCompleto

logger = structlog.get_logger(__name__)

PJE_TJMG_URL = "https://pje-consulta-publica.tjmg.jus.br/pje"


class TJMG_UnifiedCrawler(BaseCrawler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tribunal_id = "tjmg"

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        cpf_advogado: Optional[str] = None,
        **kwargs
    ) -> list[ProcessoCompleto]:

        logger.info(f"Iniciando busca TJMG para OAB {numero_oab}/{uf_oab}")

        from src.crawlers.pje_jsf_client import buscar_oab_jsf

        processos_totais: list[ProcessoCompleto] = []

        # ── 1. PJe via JSF POST (funciona!) ──
        try:
            pjes = await buscar_oab_jsf(
                base_url=PJE_TJMG_URL,
                tribunal="tjmg",
                numero_oab=numero_oab,
                uf_oab=uf_oab,
            )
            if pjes:
                logger.info(f"TJMG PJe JSF: {len(pjes)} processo(s) para OAB {numero_oab}/{uf_oab}")
                processos_totais.extend(pjes)
        except Exception as e:
            logger.debug(f"TJMG PJe JSF erro: {e}")

        # ── 2. eProc (tem reCAPTCHA — provavelmente bloqueado) ──
        try:
            from src.crawlers.eproc import EProcCrawler
            eproc = EProcCrawler(verify_ssl=False)
            epocs = await eproc.buscar_por_oab(
                numero_oab=numero_oab,
                uf_oab=uf_oab,
                tribunais=["tjmg"],
                paginas=5,
                cpf_advogado=cpf_advogado,
            )
            if epocs:
                logger.info(f"TJMG eProc: {len(epocs)} processo(s)")
                processos_totais.extend(epocs)
        except Exception as e:
            logger.debug(f"TJMG eProc erro: {e}")

        # ── 3. PJe API REST (provavelmente 404) ──
        try:
            from src.crawlers.pje import PJeCrawler
            pje = PJeCrawler(verify_ssl=False)
            pjes_api = await pje.buscar_por_oab(
                numero_oab=numero_oab,
                uf_oab=uf_oab,
                tribunais=["tjmg"],
                tamanho=100,
                cpf_advogado=cpf_advogado,
            )
            if pjes_api:
                logger.info(f"TJMG PJe API: {len(pjes_api)} processo(s)")
                processos_totais.extend(pjes_api)
        except Exception as e:
            logger.debug(f"TJMG PJe API erro: {e}")

        # Deduplicação pelo CNJ
        unicos = {p.numero_cnj: p for p in processos_totais}
        final = list(unicos.values())

        logger.info(f"Busca TJMG concluída: {len(final)} processos únicos para OAB {numero_oab}/{uf_oab}")
        return final

    async def buscar_processo(self, numero_cnj: str, **kwargs) -> Optional[ProcessoCompleto]:
        from src.crawlers.eproc import EProcCrawler
        from src.crawlers.pje import PJeCrawler

        eproc = EProcCrawler(verify_ssl=False)
        p1 = await eproc.buscar_processo(numero_cnj, tribunal="tjmg")
        if p1 and p1.partes:
            return p1

        pje = PJeCrawler(verify_ssl=False)
        p2 = await pje.buscar_processo(numero_cnj, tribunal="tjmg")
        return p2
