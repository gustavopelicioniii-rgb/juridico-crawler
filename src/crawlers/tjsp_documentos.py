"""
Crawler de documentos do TJSP via Playwright.

Acessa o portal eSaj com login e senha para listar e (opcionalmente)
baixar documentos/petições de um processo.

Requer:
    pip install playwright
    playwright install chromium

Variáveis de ambiente (.env):
    TJSP_LOGIN=seu_login
    TJSP_SENHA=sua_senha
    DOWNLOAD_DOCUMENTOS=false
    PASTA_DOCUMENTOS=./documentos
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

ESAJ_BASE = "https://esaj.tjsp.jus.br"


@dataclass
class DocumentoProcesso:
    nome: str
    data: Optional[datetime] = None
    tipo: Optional[str] = None
    tamanho: Optional[str] = None
    url_download: Optional[str] = None
    arquivo_local: Optional[Path] = None


@dataclass
class ResultadoDocumentos:
    numero_cnj: str
    documentos: list[DocumentoProcesso] = field(default_factory=list)
    erro: Optional[str] = None


async def buscar_documentos(
    numero_cnj: str,
    download: bool = False,
    pasta_destino: Optional[Path] = None,
) -> ResultadoDocumentos:
    """
    Acessa o TJSP eSaj com login/senha e lista os documentos do processo.

    Args:
        numero_cnj: Número no formato CNJ (ex: 0001234-56.2024.8.26.0001)
        download: Se True, baixa os PDFs para pasta_destino
        pasta_destino: Diretório local para salvar os PDFs

    Returns:
        ResultadoDocumentos com a lista de documentos encontrados
    """
    login = getattr(settings, "tjsp_login", None)
    senha = getattr(settings, "tjsp_senha", None)

    if not login or not senha:
        return ResultadoDocumentos(
            numero_cnj=numero_cnj,
            erro="TJSP_LOGIN e TJSP_SENHA não configurados no .env",
        )

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ResultadoDocumentos(
            numero_cnj=numero_cnj,
            erro="Playwright não instalado. Execute: pip install playwright && playwright install chromium",
        )

    if download and pasta_destino:
        pasta_destino.mkdir(parents=True, exist_ok=True)

    resultado = ResultadoDocumentos(numero_cnj=numero_cnj)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            accept_downloads=download,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            # ── 1. Login ──────────────────────────────────────────────
            logger.info("TJSP Docs: fazendo login para %s", numero_cnj)
            await page.goto(f"{ESAJ_BASE}/esaj/portal.do?servico=740000", timeout=30_000)

            await page.fill("#usernameForm", login)
            await page.fill("#passwordForm", senha)
            await page.click("input[type=submit], button[type=submit]")
            await page.wait_for_load_state("networkidle", timeout=20_000)

            if "login" in page.url.lower() or "portal" not in page.url.lower():
                resultado.erro = "Falha no login — verifique TJSP_LOGIN e TJSP_SENHA"
                return resultado

            logger.info("TJSP Docs: login OK")

            # ── 2. Buscar o processo ──────────────────────────────────
            await page.goto(
                f"{ESAJ_BASE}/cpopg/search.do?"
                f"conversationId=&cbPesquisa=NUMPROC"
                f"&dadosConsulta.valorConsulta={numero_cnj}"
                f"&dadosConsulta.tipoNuProcesso=UNIFICADO",
                timeout=30_000,
            )
            await page.wait_for_load_state("networkidle", timeout=20_000)

            # Clicar no primeiro resultado se for lista
            link = page.locator("a[href*='cpopg/show.do']").first
            if await link.count() > 0:
                await link.click()
                await page.wait_for_load_state("networkidle", timeout=20_000)

            # ── 3. Navegar até a aba de documentos ───────────────────
            aba_docs = page.locator(
                "a:has-text('Petições'), a:has-text('Documentos'), "
                "a:has-text('Autos Digitais'), #abaDocumentos"
            ).first
            if await aba_docs.count() == 0:
                resultado.erro = "Aba de documentos não encontrada (processo pode não ter autos digitais)"
                return resultado

            await aba_docs.click()
            await page.wait_for_load_state("networkidle", timeout=20_000)

            # ── 4. Extrair lista de documentos ────────────────────────
            linhas = await page.locator("table tr, .linha-documento, .documento-item").all()

            for linha in linhas:
                texto = (await linha.inner_text()).strip()
                if not texto or len(texto) < 5:
                    continue

                # Extrair data (dd/mm/aaaa)
                data_m = re.search(r"(\d{2}/\d{2}/\d{4})", texto)
                data_doc = None
                if data_m:
                    try:
                        data_doc = datetime.strptime(data_m.group(1), "%d/%m/%Y")
                    except ValueError:
                        pass

                # Tentar pegar link de download
                link_el = linha.locator("a[href*='.pdf'], a[href*='download'], a[href*='documento']").first
                url_dl = None
                if await link_el.count() > 0:
                    url_dl = await link_el.get_attribute("href")
                    if url_dl and not url_dl.startswith("http"):
                        url_dl = f"{ESAJ_BASE}{url_dl}"

                doc = DocumentoProcesso(
                    nome=texto[:200],
                    data=data_doc,
                    url_download=url_dl,
                )

                # ── 5. Download opcional ──────────────────────────────
                if download and url_dl and pasta_destino:
                    try:
                        nome_arquivo = re.sub(r"[^\w\-.]", "_", texto[:60]) + ".pdf"
                        caminho = pasta_destino / nome_arquivo
                        async with page.expect_download(timeout=30_000) as dl_info:
                            await page.goto(url_dl)
                        download_obj = await dl_info.value
                        await download_obj.save_as(caminho)
                        doc.arquivo_local = caminho
                        logger.info("TJSP Docs: baixado %s", caminho)
                    except Exception as e:
                        logger.warning("TJSP Docs: falha ao baixar %s: %s", url_dl, e)

                resultado.documentos.append(doc)

            logger.info(
                "TJSP Docs %s: %d documento(s) encontrado(s)",
                numero_cnj,
                len(resultado.documentos),
            )

        except Exception as e:
            logger.error("TJSP Docs: erro ao processar %s: %s", numero_cnj, e)
            resultado.erro = str(e)
        finally:
            await context.close()
            await browser.close()

    return resultado
