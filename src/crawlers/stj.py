"""
Crawler para o STJ (Superior Tribunal de Justiça).

Busca por OAB via portal público de consulta processual.
URL base: https://processo.stj.jus.br

Estratégia:
1. GET direto na busca por OAB → tenta extrair CNJs do HTML
2. Firecrawl como fallback (renderiza JavaScript da página de resultados)
3. Para cada CNJ, busca detalhe via API JSON do portal
"""

import structlog
import re
from typing import Optional

from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import MovimentacaoProcesso, ParteProcesso, ProcessoCompleto

logger = structlog.get_logger(__name__)

STJ_BASE = "https://processo.stj.jus.br"
STJ_PESQUISA = f"{STJ_BASE}/processo/pesquisa/"
STJ_DETALHE_API = f"{STJ_BASE}/processo/pesquisa/detalhes/"

# Padrão CNJ genérico
_RE_CNJ = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

# Número de processo STJ no formato antigo (ex: REsp 1234567/SP)
_RE_STJ_NUM = re.compile(
    r"(?:REsp|AgRg|EDcl|RHC|HC|MS|AREsp|EREsp|EAREsp|CC|RMS|AR|SLS|STA|Rcl|Pet)"
    r"[\s.]*(\d{4,8})[/\s]*([A-Z]{2})",
    re.IGNORECASE,
)


class STJCrawler(BaseCrawler):
    """Crawler para o STJ via portal público de consulta processual."""

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Referer": STJ_BASE,
        }

    # ------------------------------------------------------------------
    # BUSCA POR OAB
    # ------------------------------------------------------------------

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        paginas: int = 3,
    ) -> list[ProcessoCompleto]:
        """
        Busca processos no STJ pelo número OAB.

        Tenta extração direta do HTML; usa Firecrawl como fallback se a página
        precisar de JavaScript para renderizar os resultados.
        """
        resultados: list[ProcessoCompleto] = []
        cnjs_vistos: set[str] = set()

        for pagina in range(1, paginas + 1):
            params = {
                "tipoPesquisa": "tipoPesquisaByAdvogado",
                "termo": numero_oab,
                "aplicacao": "processos.ea",
                "pagina": str(pagina),
            }

            html = await self._fetch_pagina(STJ_PESQUISA, params)
            if not html:
                break

            cnjs = self._extrair_cnjs(html)

            if not cnjs:
                logger.debug("STJ OAB %s pág %d: nenhum CNJ encontrado no HTML direto", numero_oab, pagina)
                break

            novos = [c for c in cnjs if c not in cnjs_vistos]
            if not novos:
                break

            cnjs_vistos.update(novos)

            for cnj in novos:
                proc = await self._buscar_detalhe(cnj)
                resultados.append(proc)

            logger.info("STJ OAB %s: pág %d → +%d (total %d)", numero_oab, pagina, len(novos), len(resultados))

            if "próxima" not in html.lower() and 'page=' not in html:
                break

        if not resultados:
            logger.debug("STJ OAB %s/%s: nenhum processo encontrado", numero_oab, uf_oab)

        return resultados

    async def _fetch_pagina(self, url: str, params: dict) -> Optional[str]:
        """Tenta GET direto; fallback Firecrawl se resultado vazio."""
        try:
            resp = await self._get(url, params=params)
            html = resp.text
            # Verifica se há conteúdo relevante (não só shell JS)
            if _RE_CNJ.search(html) or "nenhum processo" in html.lower():
                return html
        except Exception as e:
            logger.debug("STJ: GET direto falhou: %s", e)

        # Fallback: Firecrawl renderiza JS
        from src.crawlers.firecrawl_client import get_firecrawl_client
        fc = get_firecrawl_client()
        if fc:
            try:
                # Monta URL completa com params
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                html_fc = await fc.scrape_html(full_url)
                if html_fc:
                    logger.debug("STJ: HTML obtido via Firecrawl (%d chars)", len(html_fc))
                    return html_fc
            except Exception as e:
                logger.debug("STJ: Firecrawl falhou: %s", e)

        return None

    # ------------------------------------------------------------------
    # BUSCA DETALHE DE UM PROCESSO
    # ------------------------------------------------------------------

    async def _buscar_detalhe(self, numero_cnj: str) -> ProcessoCompleto:
        """Busca partes e dados do processo via API JSON do portal STJ."""
        # Tenta API JSON (retorna dados estruturados quando disponível)
        try:
            url = f"{STJ_DETALHE_API}{numero_cnj}"
            resp = await self._get(url)
            if resp.status_code == 200:
                data = resp.json()
                return self._parse_detalhe_json(data, numero_cnj)
        except Exception as e:
            logger.debug("STJ: API JSON falhou para %s, tentando HTML: %s", numero_cnj, e)

        # Fallback: página HTML de detalhe
        try:
            params = {
                "tipoPesquisa": "tipoPesquisaNumeroRegistro",
                "termo": numero_cnj,
                "aplicacao": "processos.ea",
            }
            html = await self._fetch_pagina(STJ_PESQUISA, params)
            if html:
                return self._parse_detalhe_html(html, numero_cnj)
        except Exception as e:
            logger.debug("STJ: detalhe HTML falhou para %s: %s", numero_cnj, e)

        return ProcessoCompleto(numero_cnj=numero_cnj, tribunal="stj")

    async def buscar_processo(self, numero_cnj: str, **kwargs) -> Optional[ProcessoCompleto]:
        return await self._buscar_detalhe(numero_cnj)

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _extrair_cnjs(self, html: str) -> list[str]:
        """Extrai números CNJ únicos do HTML."""
        return list(dict.fromkeys(_RE_CNJ.findall(html)))

    def _parse_detalhe_json(self, data: dict, numero_cnj: str) -> ProcessoCompleto:
        """Parse da resposta JSON do endpoint de detalhes do STJ."""
        partes: list[ParteProcesso] = []

        for polo_raw in data.get("partes", []):
            tipo = (polo_raw.get("tipoParte") or polo_raw.get("tipo", "PARTE")).upper()
            nome = polo_raw.get("nome") or polo_raw.get("nomeCompleto", "")
            if not nome:
                continue
            polo = self._polo_de_tipo(tipo)
            partes.append(ParteProcesso(nome=nome.upper(), tipo_parte=tipo[:50], polo=polo))

            for adv in polo_raw.get("advogados", []):
                nome_adv = adv.get("nome", "")
                oab_raw = adv.get("oab", "")
                if nome_adv:
                    partes.append(ParteProcesso(
                        nome=nome_adv.upper(),
                        tipo_parte="ADVOGADO",
                        polo=polo,
                        oab=oab_raw[:20] if oab_raw else None,
                    ))

        movs: list[MovimentacaoProcesso] = []
        for m in data.get("andamentos", []):
            from datetime import date
            data_str = (m.get("data") or m.get("dataAndamento", ""))[:10]
            desc = m.get("descricao") or m.get("complemento", "")
            if data_str and desc:
                try:
                    d = date.fromisoformat(data_str)
                    movs.append(MovimentacaoProcesso(data_movimentacao=d, descricao=desc[:500]))
                except ValueError:
                    pass

        return ProcessoCompleto(
            numero_cnj=numero_cnj,
            tribunal="stj",
            classe_processual=data.get("classeProcessual") or data.get("classe"),
            assunto=data.get("assunto"),
            situacao=data.get("situacao"),
            partes=partes,
            movimentacoes=sorted(movs, key=lambda x: x.data_movimentacao, reverse=True),
            dados_brutos=data,
        )

    def _parse_detalhe_html(self, html: str, numero_cnj: str) -> ProcessoCompleto:
        """Extrai partes do HTML de detalhe do STJ."""
        partes: list[ParteProcesso] = []
        try:
            from selectolax.parser import HTMLParser
            tree = HTMLParser(html)

            papeis_ativos = {"RECORRENTE", "IMPETRANTE", "REQUERENTE", "AUTOR", "EXEQUENTE"}
            papeis_passivos = {"RECORRIDO", "IMPETRADO", "REQUERIDO", "RÉU", "REU", "EXECUTADO"}

            for row in tree.css("tr"):
                cells = row.css("td")
                if len(cells) < 2:
                    continue
                label = re.sub(r"[\s\xa0]+", " ", cells[0].text()).strip().upper().rstrip(":")
                valor = re.sub(r"[\s\xa0]+", " ", cells[1].text()).strip()
                if not valor or not label:
                    continue

                tipo_upper = label[:50]
                polo = self._polo_de_tipo(tipo_upper)

                if any(p in tipo_upper for p in papeis_ativos | papeis_passivos | {"ADVOGADO"}):
                    oab = None
                    oab_m = re.search(r"OAB[/\s]*([A-Z]{2})\s*(\d{3,8})", valor, re.IGNORECASE)
                    if oab_m:
                        oab = f"{oab_m.group(2)}{oab_m.group(1).upper()}"
                        valor = re.sub(r"\s*[-–]\s*OAB[/\s]*[A-Z]{2}\s*\d+", "", valor, flags=re.IGNORECASE).strip()
                    partes.append(ParteProcesso(
                        nome=valor.upper()[:300],
                        tipo_parte="ADVOGADO" if "ADVOGADO" in tipo_upper else tipo_upper,
                        polo=polo,
                        oab=oab,
                    ))
        except Exception as e:
            logger.debug("STJ: parse HTML detalhe %s: %s", numero_cnj, e)

        return ProcessoCompleto(numero_cnj=numero_cnj, tribunal="stj", partes=partes)

    def _polo_de_tipo(self, tipo: str) -> str:
        ativos = {"RECORRENTE", "IMPETRANTE", "REQUERENTE", "AUTOR", "EXEQUENTE", "APELANTE"}
        passivos = {"RECORRIDO", "IMPETRADO", "REQUERIDO", "RÉU", "REU", "EXECUTADO", "APELADO"}
        t = tipo.upper()
        if any(a in t for a in ativos):
            return "ATIVO"
        if any(p in t for p in passivos):
            return "PASSIVO"
        return "OUTROS"
