"""
Cliente HTTP para a API Firecrawl.

Firecrawl resolve scraping com JavaScript, cookies e anti-bot — usado como
fallback quando a extração direta falha (ex: partes não aparecem no eSaj).

Free tier: 500 req/mês. Configure FIRECRAWL_API_KEY no .env.
API docs: https://docs.firecrawl.dev/api-reference
"""

import logging
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"


class FirecrawlClient:
    """Cliente assíncrono para a API Firecrawl v1."""

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def scrape(
        self,
        url: str,
        formats: list[str] | None = None,
    ) -> Optional[dict]:
        """
        Faz scrape de uma URL via Firecrawl.

        Args:
            url: URL a ser raspada.
            formats: Formatos desejados. Padrão: ["html"].

        Returns:
            Dict com chave "html" (e outras opcionais), ou None em caso de erro.
        """
        if formats is None:
            formats = ["html"]

        payload = {"url": url, "formats": formats}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(FIRECRAWL_API_URL, json=payload, headers=headers)
        except Exception as e:
            logger.debug("Firecrawl: erro de rede para %s: %s", url, e)
            return None

        if resp.status_code == 401:
            logger.warning("Firecrawl: API key inválida (401)")
            return None

        if resp.status_code == 402:
            logger.warning("Firecrawl: créditos esgotados (402) — fallback desativado até recarga")
            return None

        if resp.status_code != 200:
            logger.debug("Firecrawl: status %d para %s", resp.status_code, url)
            return None

        try:
            data = resp.json()
        except Exception:
            logger.debug("Firecrawl: resposta não-JSON para %s", url)
            return None

        # Estrutura esperada: {"success": true, "data": {"html": "...", ...}}
        return data.get("data") or {}

    async def scrape_html(self, url: str) -> Optional[str]:
        """Conveniência: retorna apenas o HTML da URL, ou None se falhar."""
        data = await self.scrape(url, formats=["html"])
        if not data:
            return None
        return data.get("html") or None


def get_firecrawl_client() -> Optional[FirecrawlClient]:
    """
    Retorna um FirecrawlClient configurado, ou None se a key não estiver definida.

    Uso:
        fc = get_firecrawl_client()
        if fc:
            html = await fc.scrape_html(url)
    """
    key = settings.firecrawl_api_key
    if not key:
        return None
    return FirecrawlClient(api_key=key)
