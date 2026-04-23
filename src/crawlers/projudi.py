"""
Crawler para o sistema PROJUDI (comum em PR, GO, MT, AM).

Este crawler fornece a base para consulta direta nos tribunais PROJUDI,
complementando os dados do DataJud com scraping em tempo real.
"""

import structlog
import re
from typing import Any, Optional

from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import MovimentacaoProcesso, ParteProcesso, ProcessoCompleto

logger = structlog.get_logger(__name__)

PROJUDI_URLS: dict[str, str] = {
    "tjpr": "https://projudi.tjpr.jus.br/projudi/",
    "tjgo": "https://projudi.tjgo.jus.br/projudi/",
    "tjmt": "https://projudi.tjmt.jus.br/projudi/",
    "tjam": "https://projudi.tjam.jus.br/projudi/",
}

class ProjudiCrawler(BaseCrawler):
    """Crawler para o sistema Projudi via portal público."""

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }

    async def buscar_processo(
        self,
        numero_cnj: str,
        tribunal: str,
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        """
        Busca detalhe de um processo no Projudi.
        (Implementação inicial — foco em consulta pública via AJAX)
        """
        base = PROJUDI_URLS.get(tribunal.lower())
        if not base:
            return None
        
        logger.info("Projudi %s: buscando processo %s", tribunal.upper(), numero_cnj)
        
        # TODO: Implementar fluxo de busca pública (geralmente via consultaPublica.do)
        # Por ora, o sistema utiliza o DataJud como fonte primária para Projudi.
        return None

    def _parse_detalhe(self, html: str, numero_cnj: str, tribunal: str) -> ProcessoCompleto:
        """Parse das tabelas de partes e movimentações do Projudi."""
        # Projudi usa tabelas com IDs específicos (ex: #listaMovimentacoes)
        return ProcessoCompleto(numero_cnj=numero_cnj, tribunal=tribunal)
