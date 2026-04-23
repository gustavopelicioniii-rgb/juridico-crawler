"""
Cliente Playwright — renderização de JavaScript para SPAs que não expõem
dados no HTML estático (ex: eProc TJMG, alguns portais PJe).

Uso:
    pw = get_playwright_client()
    if pw:
        html = await pw.render_js(url)
"""
import structlog
from typing import Optional

logger = structlog.get_logger(__name__)


def get_playwright_client() -> Optional["PlaywrightClient"]:
    """Retorna cliente Playwright, ou None se não disponível."""
    try:
        from playwright.async_api import async_playwright
        return PlaywrightClient()
    except ImportError:
        logger.warning("Playwright não instalado: pip install playwright")
        return None


class PlaywrightClient:
    """
    Wrapper leve sobre Playwright para scraping de SPAs.

    Instala browsers com: python -m playwright install chromium
    """

    def __init__(self, timeout_ms: int = 30000) -> None:
        self._timeout_ms = timeout_ms
        self._pw = None
        self._pw_browser = None

    async def _get_browser(self):
        """Lazy init do browser (reaproveitado entre requisições)."""
        if self._pw_browser is None:
            from playwright.async_api import async_playwright
            self._pw = await async_playwright().start()
            self._pw_browser = await self._pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
        return self._pw_browser

    async def render_js(self, url: str, wait_for: int = 3000) -> Optional[str]:
        """
        Carrega URL com Playwright (renderiza JS) e retorna HTML final.

        Args:
            url: URL a renderizar.
            wait_for: ms para esperar após carga (default 3s).

        Returns:
            HTML da página pós-JS, ou None se falhar.
        """
        try:
            browser = await self._get_browser()
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=self._timeout_ms)
            # Aguarda um pouco mais para SPA renderizar
            await page.wait_for_timeout(wait_for)
            html = await page.content()
            await page.close()
            return html
        except Exception as e:
            logger.debug("Playwright: erro ao renderizar %s: %s", url, e)
            return None

    async def discover_api_calls(self, url: str, wait_ms: int = 5000) -> list[dict]:
        """
        Navega até URL e captura todas as requisições de API feitas pela página.

        Returns:
            Lista de dicts com {method, url, status, body_preview}.
        """
        browser = await self._get_browser()
        context = await browser.new_context()
        page = await context.new_page()

        api_calls: list[dict] = []
        seen_urls: set[str] = set()

        def on_request(request):
            u = request.url
            if "/api/" in u or "/pje/api/" in u:
                if u not in seen_urls:
                    seen_urls.add(u)
                    api_calls.append({"kind": "request", "method": request.method, "url": u})

        def on_response(response):
            u = response.url
            if "/api/" in u or "/pje/api/" in u:
                if u not in seen_urls:
                    seen_urls.add(u)
                    body = ""
                    try:
                        body = response.text()
                    except Exception:
                        pass
                    api_calls.append({
                        "kind": "response",
                        "url": u,
                        "status": response.status,
                        "body_preview": body[:300],
                    })

        page.on("request", on_request)
        page.on("response", on_response)

        try:
            await page.goto(url, wait_until="networkidle", timeout=self._timeout_ms)
            await page.wait_for_timeout(wait_ms)
        except Exception as e:
            logger.debug("Playwright discover: erro em %s: %s", url, e)

        await context.close()
        return api_calls

    async def close(self) -> None:
        """Fecha browser e playwright."""
        if self._pw_browser:
            await self._pw_browser.close()
            self._pw_browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
