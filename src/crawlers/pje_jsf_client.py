"""
Cliente JSF para portais PJe que exigem POST com ViewState (RichFaces/A4J).

Diferente do Firecrawl/Playwright — faz POST real com parâmetros JSF.
Usado como fallback quando a API REST não funciona (ex: TJMG PJe).
"""
import asyncio
import re
import structlog
from typing import Optional

import httpx
from selectolax.parser import HTMLParser

from src.parsers.estruturas import ProcessoCompleto, inferir_grau_cnj

logger = structlog.get_logger(__name__)

# Mapeamento de UF → valor numérico no formulário JSF
UF_VALOR = {
    "AC": "0", "AL": "1", "AP": "2", "AM": "3", "BA": "4",
    "CE": "5", "DF": "6", "ES": "7", "GO": "8", "MA": "9",
    "MT": "10", "MS": "11", "MG": "12", "PA": "13", "PB": "14",
    "PR": "15", "PE": "16", "PI": "17", "RJ": "18", "RN": "19",
    "RS": "20", "RO": "21", "RR": "22", "SC": "23", "SP": "24",
    "SE": "25", "TO": "26",
}


def _extrair_viewstate(html: str) -> Optional[str]:
    """Extrai o valor do campo javax.faces.ViewState do HTML."""
    tree = HTMLParser(html)
    for inp in tree.css("input"):
        if inp.attributes.get("name") == "javax.faces.ViewState":
            return inp.attributes.get("value") or None
    return None


def _extrair_campos_ocultos(html: str) -> dict[str, str]:
    """Extrai todos os campos hidden do formulário JSF."""
    campos = {}
    tree = HTMLParser(html)
    for inp in tree.css("input"):
        tp = inp.attributes.get("type", "text").lower()
        nm = inp.attributes.get("name") or ""
        vl = inp.attributes.get("value") or ""
        if tp == "hidden" and nm:
            campos[nm] = vl
    return campos


def _parse_resultados_jsf(html: str, tribunal: str) -> list[ProcessoCompleto]:
    """Extrai CNJs do HTML de resultado JSF."""
    # CNJ pattern
    cnjs = re.findall(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", html)
    # Filtrar placeholders
    cnjs = list(dict.fromkeys(c for c in cnjs if not c.startswith("9999")))
    return [
        ProcessoCompleto(numero_cnj=cnj, tribunal=tribunal, grau=inferir_grau_cnj(cnj))
        for cnj in cnjs
    ]


async def buscar_oab_jsf(
    base_url: str,
    tribunal: str,
    numero_oab: str,
    uf_oab: str,
    timeout: float = 30.0,
) -> list[ProcessoCompleto]:
    """
    Faz busca por OAB em portal PJe via POST JSF.

    Funciona para tribunais que usam RichFaces/A4J com ViewState,
    impossível de automatizar com requests simples sem este fluxo.

    Fluxo:
      1. GET na página do formulário → obtém ViewState + campos ocultos
      2. POST com OAB + UF + ViewState + campos ocultos
      3. Parse dos CNJs no HTML de resposta
    """
    form_url = f"{base_url}/ConsultaPublica/listView.seam"
    uf_valor = UF_VALOR.get(uf_oab.upper())
    if not uf_valor:
        logger.debug("UF %s não tem valor numérico no formulário JSF", uf_oab)
        return []

    headers_post = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    async with httpx.AsyncClient(
        verify=False,
        follow_redirects=True,
        timeout=timeout,
    ) as client:
        # ── Passo 1: GET para obter ViewState e campos ocultos ──
        try:
            resp_get = await client.get(form_url)
            if resp_get.status_code != 200:
                logger.debug("JSF GET %s retornou %d", tribunal, resp_get.status_code)
                return []
        except Exception as e:
            logger.debug("JSF GET %s erro: %s", tribunal, e)
            return []

        html_inicial = resp_get.text
        view_state = _extrair_viewstate(html_inicial)
        if not view_state:
            logger.debug("JSF: ViewState não encontrado em %s", tribunal)
            return []

        campos = _extrair_campos_ocultos(html_inicial)

        # ── Passo 2: POST com formulário de busca ──
        post_data = dict(campos)
        post_data["javax.faces.ViewState"] = view_state
        post_data["fPP:Decoration:estadoComboOAB"] = uf_valor
        post_data["fPP:Decoration:numeroOAB"] = numero_oab
        post_data["fPP:searchProcessos"] = "Pesquisar"
        post_data["fPP"] = "fPP"

        try:
            resp_post = await client.post(form_url, data=post_data, headers=headers_post)
        except Exception as e:
            logger.debug("JSF POST %s erro: %s", tribunal, e)
            return []

        if resp_post.status_code != 200:
            logger.debug("JSF POST %s retornou %d", tribunal, resp_post.status_code)
            return []

        # ── Passo 3: Parse dos CNJs ──
        html_resultado = resp_post.text
        processos = _parse_resultados_jsf(html_resultado, tribunal)

        if processos:
            logger.info(
                "JSF %s: %d processo(s) para OAB %s/%s",
                tribunal, len(processos), numero_oab, uf_oab,
            )

        return processos
