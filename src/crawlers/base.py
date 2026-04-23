"""
Classe base para todos os crawlers.
Implementa rate limiting, retry com backoff exponencial, logging estruturado,
hooks para proxy pool rotativo e solver de CAPTCHA.
"""

import asyncio
import itertools
import os
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional
import structlog

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.config import settings
from src.parsers.estruturas import ProcessoCompleto

logger = structlog.get_logger(__name__)


# ============================================================
# Proxy pool rotativo
# ============================================================
class ProxyPool:
    """
    Pool rotativo de proxies residenciais/datacenter.

    Uso:
        pool = ProxyPool.from_env()  # lê PROXY_LIST="http://user:pass@host:port,..."
        crawler = TJSPCrawler(proxy_pool=pool)

    Se nenhum proxy estiver configurado, a instância é "no-op" — .next() retorna None
    e o httpx.AsyncClient é construído sem parâmetro proxy.
    """

    def __init__(self, proxies: Optional[list[str]] = None):
        self.proxies: list[str] = [p.strip() for p in (proxies or []) if p.strip()]
        self._cycle = itertools.cycle(self.proxies) if self.proxies else None

    @classmethod
    def from_env(cls) -> "ProxyPool":
        # Lê via settings (pydantic-settings carrega o .env corretamente).
        # os.getenv("PROXY_LIST") não funciona pois pydantic-settings não popula os.environ.
        try:
            from src.config import settings
            raw = settings.proxy_list or ""
        except Exception:
            raw = os.getenv("PROXY_LIST", "")
        proxies = [p.strip() for p in raw.split(",") if p.strip()] if raw else []
        if proxies:
            logger.debug("ProxyPool: %d proxy(s) carregado(s) do .env", len(proxies))
        return cls(proxies)

    def next(self) -> Optional[str]:
        if not self._cycle:
            return None
        return next(self._cycle)

    def random(self) -> Optional[str]:
        if not self.proxies:
            return None
        return random.choice(self.proxies)

    def __bool__(self) -> bool:
        return bool(self.proxies)


# ============================================================
# CAPTCHA solver (contrato — implementação depende do provedor)
# ============================================================
class CaptchaSolver:
    """
    Interface para solvers de CAPTCHA. Implementações concretas devem usar provedores
    como 2Captcha, CapSolver, Anti-Captcha, etc.

    Exemplo de uso pelas subclasses:
        if self.captcha_solver and resposta.status_code == 403:
            token = await self.captcha_solver.resolve_recaptcha_v2(
                sitekey="6Lc...",
                url="https://esaj.tjsp.jus.br/...",
            )
            # reenviar request com o token
    """

    async def resolve_recaptcha_v2(self, sitekey: str, url: str) -> Optional[str]:
        raise NotImplementedError("Configure um solver concreto (TwoCaptchaSolver, CapSolverSolver, etc.)")

    async def resolve_hcaptcha(self, sitekey: str, url: str) -> Optional[str]:
        raise NotImplementedError

    async def resolve_imagem(self, imagem_base64: str) -> Optional[str]:
        raise NotImplementedError

def is_retryable_erro(e: BaseException) -> bool:
    if isinstance(e, (httpx.TimeoutException, httpx.NetworkError, httpx.ReadError)):
        return True
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        # 429 → rate limit, 502/503 → infra transitória → retry
        # 500 → erro do servidor (bug), 504 → gateway morto → NÃO retry
        if code == 429 or code in (502, 503):
            return True
        # 500 e 504 frequentemente não são transitórios (TST legado, TRF1 etc.)
        # Permite 1 retry apenas para dar chance em falhas momentâneas
        if code in (500, 504):
            # tenacity conta tentativas: se já é re-tentativa, não tenta mais
            # Usamos o atributo da exceção para saber — na prática, a tenacity
            # vai chamar is_retryable apenas quando já decidiu tentar de novo,
            # então deixamos True mas com stop_after_attempt=2 nos callers que
            # precisam de menos retries. Aqui retornamos False para não retry.
            return False
    return False


class RateLimiter:
    """Token bucket rate limiter para controlar requisições por minuto."""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.min_interval = 60.0 / requests_per_minute
        self._last_request: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_request = time.monotonic()


class BaseCrawler(ABC):
    """
    Classe base para crawlers jurídicos.

    Subclasses devem implementar `buscar_processo` e `_get_headers`.
    """

    def __init__(
        self,
        requests_per_minute: Optional[int] = None,
        max_retries: Optional[int] = None,
        timeout: float = 30.0,
        proxy_pool: Optional[ProxyPool] = None,
        captcha_solver: Optional[CaptchaSolver] = None,
        verify_ssl: bool = True,
    ):
        self.rate_limiter = RateLimiter(
            requests_per_minute or settings.crawler_requests_per_minute
        )
        self.max_retries = max_retries or settings.crawler_max_retries
        self.timeout = timeout
        # Proxy pool: se não foi passado, tenta ler do ambiente — no-op se vazio
        self.proxy_pool = proxy_pool if proxy_pool is not None else ProxyPool.from_env()
        self.captcha_solver = captcha_solver
        # verify_ssl=False desabilita verificação de cert SSL — útil para TJs com
        # certificados ICP-Brasil não reconhecidos pelo Python por padrão.
        # Com proxy, sempre False (proxy faz interceptação SSL própria).
        self.verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "BaseCrawler":
        # Add basic TCP limits
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)

        # Proxy: pega um do pool no momento da criação do client
        proxy = self.proxy_pool.next() if self.proxy_pool else None
        if proxy:
            logger.debug("Crawler %s usando proxy %s", type(self).__name__, proxy.split("@")[-1])

        client_kwargs: dict[str, Any] = dict(
            headers=self._get_headers(),
            timeout=httpx.Timeout(self.timeout),
            follow_redirects=True,
            limits=limits,
        )
        if proxy:
            client_kwargs["proxy"] = proxy
            # Proxies residenciais fazem interceptação SSL — sempre verify=False.
            client_kwargs["verify"] = False
        elif not self.verify_ssl:
            # Conexão direta, mas verify_ssl=False foi solicitado.
            # Necessário para TJs com certificados ICP-Brasil não reconhecidos
            # pela cadeia de CAs padrão do Python/httpx (ex: TJMG, TJRJ, TJSC...).
            client_kwargs["verify"] = False

        self._client = httpx.AsyncClient(**client_kwargs)
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Use o crawler como context manager: async with crawler as c:")
        return self._client

    def _get_headers(self) -> dict[str, str]:
        """Headers padrão — pode ser sobrescrito por subclasses."""
        return {
            "User-Agent": "JuridicoCrawler/1.0 (juridico-crawler; contato@example.com)",
            "Accept": "application/json",
        }

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        """GET com rate limiting e retry."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=settings.crawler_retry_delay, min=2, max=60),
            retry=retry_if_exception(is_retryable_erro),
        ):
            with attempt:
                await self.rate_limiter.acquire()
                logger.debug("GET %s", url)
                response = await self.client.get(url, **kwargs)
                response.raise_for_status()
                return response
        raise RuntimeError(f"Falha após {self.max_retries} tentativas: GET {url}")

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        """POST com rate limiting e retry."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=settings.crawler_retry_delay, min=2, max=60),
            retry=retry_if_exception(is_retryable_erro),
        ):
            with attempt:
                await self.rate_limiter.acquire()
                logger.debug("POST %s", url)
                response = await self.client.post(url, **kwargs)
                response.raise_for_status()
                return response
        raise RuntimeError(f"Falha após {self.max_retries} tentativas: POST {url}")

    @abstractmethod
    async def buscar_processo(self, numero_cnj: str, **kwargs: Any) -> Optional[ProcessoCompleto]:
        """
        Busca um processo pelo número CNJ.
        Retorna ProcessoCompleto ou None se não encontrado.
        """
        ...
