"""
Crawler para o sistema eProc — usado pelos TRFs (Tribunais Regionais Federais).
Suporta busca por OAB via consulta pública.

Tribunais:
  TRF1: https://eproc1g.trf1.jus.br/eproc/externo_controlador.php
  TRF2: https://eproc.trf2.jus.br/eproc/externo_controlador.php
  TRF3: https://eproc.trf3.jus.br/eproc/externo_controlador.php
  TRF4: https://eproc.trf4.jus.br/eproc/externo_controlador.php
  TRF5: https://eproc.trf5.jus.br/eproc/externo_controlador.php
  TRF6: https://eproc.trf6.jus.br/eproc/externo_controlador.php
"""

import asyncio
import structlog
import re
from datetime import date, datetime
from typing import Any, Optional

from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import MovimentacaoProcesso, ParteProcesso, ProcessoCompleto

logger = structlog.get_logger(__name__)

EPROC_URLS: dict[str, str] = {
    # TRF2 — acessível externamente (São Paulo / Rio de Janeiro, 2ª Região)
    "trf2": "https://eproc.trf2.jus.br/eproc/externo_controlador.php",
    # TRF4 — URL corrigida (migrou de /eproc/ para /eproc2trf4/ em 2024)
    "trf4": "https://eproc.trf4.jus.br/eproc2trf4/externo_controlador.php",
    # TJMG — eProc estadual (SPA/JS; requer Firecrawl para renderização)
    "tjmg": "https://eproc-consulta-publica-1g.tjmg.jus.br/eproc/externo_controlador.php",
    # TRF1, TRF3, TRF5, TRF6 — Rede JUS interna (DNS não resolve externamente)
    # "trf1": "https://eproc1g.trf1.jus.br/eproc/externo_controlador.php",
    # "trf3": "https://eproc.trf3.jus.br/eproc/externo_controlador.php",
    # "trf5": "https://eproc.trf5.jus.br/eproc/externo_controlador.php",
    # "trf6": "https://eproc.trf6.jus.br/eproc/externo_controlador.php",
}

TODOS_TRIBUNAIS_EPROC = list(EPROC_URLS.keys())


class EProcCrawler(BaseCrawler):
    """Crawler para o sistema eProc dos TRFs."""

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

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        tribunais: Optional[list[str]] = None,
        paginas: int = 5,
        max_concorrentes: int = 10,
        cpf_advogado: Optional[str] = None,
    ) -> list[ProcessoCompleto]:
        """
        Busca processos em todos os TRFs eProc em paralelo.
        """
        alvos = tribunais or TODOS_TRIBUNAIS_EPROC
        semaphore = asyncio.Semaphore(max_concorrentes)

        async def consultar(tribunal: str) -> list[ProcessoCompleto]:
            if tribunal not in EPROC_URLS:
                return []
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self._buscar_oab_tribunal(
                            tribunal=tribunal,
                            numero_oab=numero_oab,
                            uf_oab=uf_oab,
                            paginas=paginas,
                            cpf_advogado=cpf_advogado,
                        ),
                        timeout=20.0
                    )
                except asyncio.TimeoutError:
                    logger.debug("eProc %s: timeout paralelo OAB %s", tribunal, numero_oab)
                    return []
                except Exception as e:
                    logger.debug("eProc %s: erro paralelo OAB %s: %s", tribunal, numero_oab, e)
                    return []

        tarefas = [consultar(t) for t in alvos]
        listas = await asyncio.gather(*tarefas)
        
        resultados: list[ProcessoCompleto] = []
        for lista in listas:
            resultados.extend(lista)
            
        return resultados

    async def _buscar_oab_tribunal(
        self,
        tribunal: str,
        numero_oab: str,
        uf_oab: str,
        paginas: int,
        cpf_advogado: Optional[str] = None,
    ) -> list[ProcessoCompleto]:
        """Busca por OAB em um TRF específico via eProc."""
        url = EPROC_URLS[tribunal]
        resultados: list[ProcessoCompleto] = []

        for pagina in range(paginas):
            params = {
                "acao": "processo_consulta_publica",
                "acao_origem": "processo_consulta_publica",
                "num_oab": numero_oab if numero_oab else "",
                "uf_oab": uf_oab.upper() if uf_oab else "",
                "num_documento": cpf_advogado if cpf_advogado else "",
                "tipo_busca": "OAB" if not cpf_advogado else "DOC",
                "paginaAtual": str(pagina + 1),
            }

            try:
                resp = await self._get(url, params=params)
                html = resp.text
                processos_pagina = self._parse_lista(html, tribunal)
                if processos_pagina:
                    resultados.extend(processos_pagina)
                    if "próxima" not in html.lower() and "Próxima" not in html:
                        break
                    continue
            except Exception as e:
                logger.debug("eProc %s pág %d erro direto: %s", tribunal, pagina + 1, e)

            # Fallback Firecrawl para renderizar JS do eProc (alguns TRFs protegem com JS)
            from src.crawlers.firecrawl_client import get_firecrawl_client
            fc = get_firecrawl_client()
            if fc:
                try:
                    from urllib.parse import urlencode
                    full_url = f"{url}?{urlencode(params)}"
                    html_fc = await fc.scrape_html(full_url)
                    if html_fc:
                        processos_pagina = self._parse_lista(html_fc, tribunal)
                        if processos_pagina:
                            resultados.extend(processos_pagina)
                            if "próxima" not in html_fc.lower() and "Próxima" not in html_fc:
                                break
                            continue
                except Exception as e:
                    logger.debug("eProc %s pág %d: Firecrawl falhou: %s", tribunal, pagina + 1, e)
            
            # Se chegou aqui sem processos na página, interrompe
            break

        return resultados

    async def buscar_processo(
        self,
        numero_cnj: str,
        tribunal: str,
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        """Busca detalhe de um processo específico no eProc."""
        url = EPROC_URLS.get(tribunal)
        if not url:
            return None

        params = {
            "acao": "processo_consulta_publica",
            "num_processo": numero_cnj,
        }

        try:
            resp = await self._get(url, params=params)
            if resp.status_code == 200:
                return self._parse_detalhe(resp.text, numero_cnj, tribunal)
        except Exception as e:
            logger.debug("eProc %s: erro direto no detalhe %s: %s", tribunal, numero_cnj, e)

        # Fallback Firecrawl para detalhe do eProc
        from src.crawlers.firecrawl_client import get_firecrawl_client
        fc = get_firecrawl_client()
        if fc:
            try:
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                html_fc = await fc.scrape_html(full_url)
                if html_fc:
                    return self._parse_detalhe(html_fc, numero_cnj, tribunal)
            except Exception as e:
                logger.debug("eProc %s: Firecrawl falhou no detalhe %s: %s", tribunal, numero_cnj, e)

        return None

    def _parse_lista(self, html: str, tribunal: str) -> list[ProcessoCompleto]:
        """Extrai lista de processos do HTML do eProc."""
        # Números CNJ por regex (fallback universal)
        padrao = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
        numeros = list(dict.fromkeys(re.findall(padrao, html)))

        processos = []
        for numero in numeros:
            # Tenta extrair classe e data do contexto ao redor do número
            idx = html.find(numero)
            trecho = html[max(0, idx - 200):idx + 400] if idx >= 0 else ""

            data_dist = None
            m = re.search(r"(\d{2}/\d{2}/\d{4})", trecho)
            if m:
                try:
                    data_dist = datetime.strptime(m.group(1), "%d/%m/%Y").date()
                except ValueError:
                    pass

            processos.append(ProcessoCompleto(
                numero_cnj=numero,
                tribunal=tribunal,
                data_distribuicao=data_dist,
            ))

        return processos

    def _parse_detalhe(self, html: str, numero_cnj: str, tribunal: str) -> ProcessoCompleto:
        """Parse do HTML de detalhe do processo no eProc."""
        try:
            from selectolax.parser import HTMLParser
            tree = HTMLParser(html)

            def txt(sel: str) -> Optional[str]:
                n = tree.css_first(sel)
                return n.text(strip=True) if n else None

            partes: list[ParteProcesso] = []

            # eProc lista partes em tabela com labels Autor/Réu/Advogado
            for row in tree.css("tr"):
                cells = row.css("td")
                if len(cells) < 2:
                    continue
                label = cells[0].text(strip=True).upper().rstrip(":")
                valor = cells[1].text(strip=True)
                if not valor or label not in {
                    "AUTOR", "RÉU", "REU", "ADVOGADO", "EXEQUENTE",
                    "EXECUTADO", "APELANTE", "APELADO", "RECLAMANTE", "RECLAMADO"
                }:
                    continue

                polo = "ATIVO" if label in ("AUTOR", "EXEQUENTE", "APELANTE", "RECLAMANTE") else (
                    "PASSIVO" if label in ("RÉU", "REU", "EXECUTADO", "APELADO", "RECLAMADO") else "OUTROS"
                )
                oab = None
                oab_m = re.search(r"OAB[/\s]*(\w{2})\s*(\d+)", valor, re.IGNORECASE)
                if oab_m:
                    oab = f"{oab_m.group(2)}{oab_m.group(1).upper()}"
                    valor = re.sub(r"\s*[-–]\s*OAB[/\s]*\w{2}\s*\d+", "", valor, flags=re.IGNORECASE).strip()

                partes.append(ParteProcesso(
                    nome=valor.upper(),
                    tipo_parte=label,
                    polo=polo,
                    oab=oab,
                ))

            return ProcessoCompleto(
                numero_cnj=numero_cnj,
                tribunal=tribunal,
                partes=partes,
            )
        except Exception as e:
            logger.error("eProc parse detalhe %s: %s", numero_cnj, e)
            return ProcessoCompleto(numero_cnj=numero_cnj, tribunal=tribunal)
