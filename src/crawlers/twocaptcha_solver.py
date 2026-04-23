"""
2Captcha solver para CAPTCHAs.

Uso:
    solver = TwoCaptchaSolver(api_key="sua_chave_2captcha")
    token = await solver.resolve_recaptcha_v2(sitekey, url)
"""
import asyncio
import httpx
import logging
import re
from typing import Optional

from src.crawlers.base import CaptchaSolver

logger = logging.getLogger(__name__)


class TwoCaptchaSolver(CaptchaSolver):
    """Implementação do CaptchaSolver usando o serviço 2Captcha."""

    BASE_URL = "https://2captcha.com"

    def __init__(self, api_key: str, *, timeout: int = 120, poll_interval: int = 5):
        self.api_key = api_key
        self.timeout = timeout
        self.poll_interval = poll_interval

    async def resolve_recaptcha_v2(self, sitekey: str, url: str) -> Optional[str]:
        """
        Resolve um reCAPTCHA v2 via 2Captcha.

        Retorna o token g-recaptcha-response ou None se falhar.
        """
        try:
            return await self._solve_recaptcha_v2(sitekey, url)
        except Exception as e:
            logger.error("2Captcha error: %s", e)
            return None

    async def _solve_recaptcha_v2(self, sitekey: str, url: str) -> str:
        """Implementação real do solver reCAPTCHA v2."""
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. Submeter CAPTCHA
            submit_url = (
                f"{self.BASE_URL}/in.php"
                f"?key={self.api_key}"
                f"&method=userrecaptcha"
                f"&googlekey={sitekey}"
                f"&pageurl={httpx.URL(url).ascii_query_string if '?' in url else url}"
            )
            r = await client.get(submit_url)
            text = r.text.strip()

            if "ERROR" in text:
                raise ValueError(f"2Captcha submit error: {text}")

            # Extrair CAPTCHA ID
            match = re.search(r"OK\|(\d+)", text)
            if not match:
                raise ValueError(f"Unexpected 2Captcha response: {text}")

            captcha_id = match.group(1)
            logger.info("2Captcha: CAPTCHA %s submetido, aguardando...", captcha_id)

            # 2. Pollar resultado
            for _ in range(self.timeout // self.poll_interval):
                await asyncio.sleep(self.poll_interval)

                result_url = (
                    f"{self.BASE_URL}/res.php"
                    f"?key={self.api_key}"
                    f"&action=get"
                    f"&id={captcha_id}"
                )
                r = await client.get(result_url)
                result = r.text.strip()

                if result == "CAPCHA_NOT_READY":
                    continue

                if "ERROR" in result:
                    raise ValueError(f"2Captcha result error: {result}")

                if result.startswith("OK|"):
                    token = result[3:]
                    logger.info("2Captcha: CAPTCHA %s resolvido com sucesso", captcha_id)
                    return token

            raise TimeoutError(f"2Captcha: timeout após {self.timeout}s")

    async def resolve_hcaptcha(self, sitekey: str, url: str) -> Optional[str]:
        """Resolve hCaptcha via 2Captcha."""
        try:
            return await self._solve_hcaptcha(sitekey, url)
        except Exception as e:
            logger.error("2Captcha hCaptcha error: %s", e)
            return None

    async def _solve_hcaptcha(self, sitekey: str, url: str) -> str:
        """Implementação real do solver hCaptcha."""
        async with httpx.AsyncClient(timeout=30) as client:
            submit_url = (
                f"{self.BASE_URL}/in.php"
                f"?key={self.api_key}"
                f"&method=hcaptcha"
                f"&sitekey={sitekey}"
                f"&pageurl={url}"
            )
            r = await client.get(submit_url)
            text = r.text.strip()

            if "ERROR" in text:
                raise ValueError(f"2Captcha hCaptcha submit error: {text}")

            match = re.search(r"OK\|(\d+)", text)
            if not match:
                raise ValueError(f"Unexpected 2Captcha response: {text}")

            captcha_id = match.group(1)
            logger.info("2Captcha: hCaptcha %s submetido, aguardando...", captcha_id)

            for _ in range(self.timeout // self.poll_interval):
                await asyncio.sleep(self.poll_interval)

                result_url = (
                    f"{self.BASE_URL}/res.php"
                    f"?key={self.api_key}"
                    f"&action=get"
                    f"&id={captcha_id}"
                )
                r = await client.get(result_url)
                result = r.text.strip()

                if result == "CAPCHA_NOT_READY":
                    continue
                if "ERROR" in result:
                    raise ValueError(f"2Captcha hCaptcha result error: {result}")
                if result.startswith("OK|"):
                    return result[3:]

            raise TimeoutError(f"2Captcha hCaptcha: timeout após {self.timeout}s")

    async def resolve_imagem(self, imagem_base64: str) -> Optional[str]:
        """Resolve CAPTCHA de imagem via 2Captcha."""
        # PLACEHOLDER — implement only if needed
        raise NotImplementedError("resolve_imagem: ainda não implementado")
