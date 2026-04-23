"""
Crawler genérico para o sistema PJe — busca por OAB e por número CNJ.
Cobre: todos os 24 TRTs, TJDFT, TST e TJs que usam PJe.
"""

import asyncio
import structlog
import re
from typing import Any, Optional
from datetime import date, datetime

from bs4 import BeautifulSoup

from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import (
    MovimentacaoProcesso,
    ParteProcesso,
    ProcessoCompleto,
    inferir_grau_cnj,
)

logger = structlog.get_logger(__name__)

# URL base de cada tribunal no PJe
PJE_URLS: dict[str, str] = {
    # Tribunais Regionais do Trabalho (todos os 24)
    "trt1":  "https://pje.trt1.jus.br/consultaprocessual",
    "trt2":  "https://pje.trt2.jus.br/consultaprocessual",
    "trt3":  "https://pje.trt3.jus.br/consultaprocessual",
    "trt4":  "https://pje.trt4.jus.br/consultaprocessual",
    "trt5":  "https://pje.trt5.jus.br/consultaprocessual",
    "trt6":  "https://pje.trt6.jus.br/consultaprocessual",
    "trt7":  "https://pje.trt7.jus.br/consultaprocessual",
    "trt8":  "https://pje.trt8.jus.br/consultaprocessual",
    "trt9":  "https://pje.trt9.jus.br/consultaprocessual",
    "trt10": "https://pje.trt10.jus.br/consultaprocessual",
    "trt11": "https://pje.trt11.jus.br/consultaprocessual",
    "trt12": "https://pje.trt12.jus.br/consultaprocessual",
    "trt13": "https://pje.trt13.jus.br/consultaprocessual",
    "trt14": "https://pje.trt14.jus.br/consultaprocessual",
    "trt15": "https://pje.trt15.jus.br/consultaprocessual",
    "trt16": "https://pje.trt16.jus.br/consultaprocessual",
    "trt17": "https://pje.trt17.jus.br/consultaprocessual",
    "trt18": "https://pje.trt18.jus.br/consultaprocessual",
    "trt19": "https://pje.trt19.jus.br/consultaprocessual",
    "trt20": "https://pje.trt20.jus.br/consultaprocessual",
    "trt21": "https://pje.trt21.jus.br/consultaprocessual",
    "trt22": "https://pje.trt22.jus.br/consultaprocessual",
    "trt23": "https://pje.trt23.jus.br/consultaprocessual",
    "trt24": "https://pje.trt24.jus.br/consultaprocessual",
    # Tribunal Superior do Trabalho
    "tst":   "https://pje.tst.jus.br/consultaprocessual",
    # Tribunais Regionais Federais via PJe
    "trf1":  "https://pje.trf1.jus.br/consultaprocessual",
    "trf3":  "https://pje.trf3.jus.br/pje",
    "trf5":  "https://pje.trf5.jus.br/pje",
    # Tribunais de Justiça Estaduais via PJe
    "tjba":  "https://pje.tjba.jus.br/pje",
    "tjpe":  "https://pje.tjpe.jus.br/pje",
    "tjce":  "https://pje.tjce.jus.br/pje",
    "tjrn":  "https://pje.tjrn.jus.br/pje",
    "tjma":  "https://pje.tjma.jus.br/pje",
    "tjpi":  "https://pje.tjpi.jus.br/pje",
    "tjal":  "https://pje.tjal.jus.br/pje",
    "tjse":  "https://pje.tjse.jus.br/pje",
    "tjam":  "https://pje.tjam.jus.br/pje",
    "tjro":  "https://pje.tjro.jus.br/pje",
    "tjac":  "https://pje.tjac.jus.br/pje",
    "tjdft": "https://pje.tjdft.jus.br/consultaprocessual",
    "tjmg":  "https://pje-consulta-publica.tjmg.jus.br/pje",
}

TODOS_TRIBUNAIS_PJE = list(PJE_URLS.keys())


class PJeCrawler(BaseCrawler):
    """Crawler PJe com suporte a busca por OAB via API REST não-oficial."""

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }

    # ------------------------------------------------------------------
    # BUSCA POR OAB EM UM TRIBUNAL
    # ------------------------------------------------------------------

    async def buscar_por_oab_tribunal(
        self,
        tribunal: str,
        numero_oab: str,
        uf_oab: str,
        pagina: int = 0,
        tamanho: int = 100,
        cpf_advogado: Optional[str] = None,
    ) -> list[ProcessoCompleto]:
        """
        Busca processos por OAB em um tribunal PJe específico.
        Usa a API REST pública do PJe (/api/v1/advogado/{oab}/processos).
        """
        base = PJE_URLS.get(tribunal.lower())
        if not base:
            raise ValueError(f"Tribunal PJe não configurado: {tribunal}")

        # Endpoint público da API REST do PJe para busca por advogado
        url = f"{base}/api/v1/advogado/{numero_oab}/processos"
        params = {
            "uf": uf_oab.upper(),
            "pagina": pagina,
            "tamanhoPagina": tamanho,
        }

        try:
            resp = await self._get(url, params=params)

            # Verifica Content-Type antes de tentar .json() —
            # vários tribunais retornam 200/202 com HTML (portal de login, splash)
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                logger.debug(
                    "PJe %s OAB %s: API retornou não-JSON (CT=%s, status=%d) — tentando HTML",
                    tribunal, numero_oab, ct, resp.status_code,
                )
                # Resposta não-JSON pode conter resultados renderizados por JS
                return await self._buscar_oab_html(base, numero_oab, uf_oab, tribunal)

            data = resp.json()
            resultados = self._parse_lista_api(data, tribunal)
            # API respondeu com JSON válido → resultado confiável (mesmo que vazio)
            if not resultados:
                logger.debug(
                    "PJe %s OAB %s: API JSON respondeu com 0 resultados (chaves=%s)",
                    tribunal, numero_oab,
                    list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                )
            return resultados

        except Exception as e:
            # Erro de rede, timeout, status inesperado — tenta HTML como fallback
            logger.debug("PJe %s OAB %s: erro na API REST: %s", tribunal, numero_oab, e)

        # Fallback — endpoint de consulta pública HTML (só chega aqui em caso de erro real)
        return await self._buscar_oab_html(base, numero_oab, uf_oab, tribunal, cpf_advogado=cpf_advogado)

    async def _buscar_oab_html(
        self,
        base_url: str,
        numero_oab: str,
        uf_oab: str,
        tribunal: str,
        cpf_advogado: Optional[str] = None,
    ) -> list[ProcessoCompleto]:
        """
        Fallback HTML para tribunais cuja API REST retornou não-JSON.

        Fluxo:
          1. GET consultaPublica/listView.seam — parse direto do HTML estático
          2. Se status 202 (processando) → sem Firecrawl, retorna []
          3. Se HTML sem CNJ + status 200 → Firecrawl para renderizar JS
        """
        url = f"{base_url}/consultaPublica/listView.seam"
        params = {
            "tipoConsulta": "advogado",
            "numeroOAB": numero_oab if numero_oab else "",
            "ufOAB": uf_oab.upper() if uf_oab else "",
            "cpfCnpj": cpf_advogado if cpf_advogado else "",
        }
        html_ok = False
        try:
            resp = await self._get(url, params=params)

            # 202 Accepted = servidor recebeu mas ainda está processando.
            # Firecrawl também vai encontrar a mesma página "aguardando" — não tenta.
            if resp.status_code == 202:
                logger.debug(
                    "PJe %s OAB %s: listView retornou 202 Accepted (não-pronto) — pulando Firecrawl",
                    tribunal, numero_oab,
                )
                return []

            html = resp.text
            html_ok = True  # página carregou com 200 — vale tentar Firecrawl se não tiver CNJ
            # Verifica se o HTML já contém números CNJ (renderizado server-side)
            if re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", html):
                processos = self._parse_lista_html(html, tribunal)
                if processos:
                    return processos
        except Exception as e:
            logger.debug("PJe %s: GET direto falhou para OAB %s: %s", tribunal, numero_oab, e)

        # Fallback Firecrawl — só vale a pena se a página carregou (200) mas estava vazia
        # (provavelmente renderizada por JavaScript no cliente)
        if not html_ok:
            return []

        from src.crawlers.firecrawl_client import get_firecrawl_client
        fc = get_firecrawl_client()
        if fc:
            try:
                from urllib.parse import urlencode
                full_url = f"{url}?{urlencode(params)}"
                html_fc = await fc.scrape_html(full_url)
                if html_fc:
                    parsed = self._parse_lista_html(html_fc, tribunal)
                    if parsed:
                        return parsed
            except Exception as e:
                logger.debug("PJe %s: Firecrawl falhou para OAB %s: %s", tribunal, numero_oab, e)

        # Último recurso: Playwright para interagir com formulário JSF (ex: TJMG PJe)
        return await self._scrape_pje_jsf_playwright(tribunal, numero_oab, uf_oab)

    # ------------------------------------------------------------------
    # SCRAPING JSF VIA PLAYWRIGHT (para portais que exigem interação com formulário)
    # ------------------------------------------------------------------

    async def _scrape_pje_jsf_playwright(
        self,
        tribunal: str,
        numero_oab: str,
        uf_oab: str,
    ) -> list[ProcessoCompleto]:
        """
        Scraper Playwright para portais PJe que usam formulário JSF com POST.

        Alguns tribunais (ex: TJMG PJe) exigem que o formulário seja submetido
        via POST com ViewState do JSF — impossível de fazer com requests simples.
        O Playwright renderiza o browser e interage com o formulário.

        Returns:
            Lista de ProcessoCompleto (só com numero_cnj preenchido inicialmente).
        """
        try:
            pw_client = self._get_playwright_client()
            if not pw_client:
                logger.debug("PJe %s: Playwright não disponível para JSF", tribunal)
                return []
        except Exception:
            return []

        browser = None
        try:
            from playwright.async_api import async_playwright

            pw = await async_playwright().start()
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            base_url = PJE_URLS.get(tribunal.lower())
            if not base_url:
                return []

            form_url = f"{base_url}/ConsultaPublica/listView.seam"

            # 1. Carregar página inicial do formulário
            await page.goto(form_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)

            # 2. Selecionar UF (valor numérico)
            uf_map = {
                "AC": "0", "AL": "1", "AP": "2", "AM": "3", "BA": "4",
                "CE": "5", "DF": "6", "ES": "7", "GO": "8", "MA": "9",
                "MT": "10", "MS": "11", "MG": "12", "PA": "13", "PB": "14",
                "PR": "15", "PE": "16", "PI": "17", "RJ": "18", "RN": "19",
                "RS": "20", "RO": "21", "RR": "22", "SC": "23", "SP": "24",
                "SE": "25", "TO": "26",
            }
            uf_value = uf_map.get(uf_oab.upper())
            if uf_value:
                try:
                    await page.select_option(
                        'select[name="fPP:Decoration:estadoComboOAB"]',
                        uf_value,
                        timeout=5000,
                    )
                except Exception as e:
                    logger.debug("PJe %s: erro ao selecionar UF %s: %s", tribunal, uf_oab, e)

            # 3. Preencher número OAB
            await page.fill('input[name="fPP:Decoration:numeroOAB"]', numero_oab, timeout=5000)

            # 4. Clicar em Pesquisar
            await page.click('input[name="fPP:searchProcessos"]', timeout=5000)

            # 5. Aguardar resposta
            await page.wait_for_timeout(5000)

            # 6. Extrair CNJs do HTML resultante
            html = await page.content()
            cnjs = re.findall(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", html)
            cnjs = list(dict.fromkeys(c for c in cnjs if not c.startswith("9999")))

            if cnjs:
                logger.info(
                    "PJe %s Playwright: %d processo(s) para OAB %s/%s",
                    tribunal, len(cnjs), numero_oab, uf_oab,
                )

            return [
                ProcessoCompleto(
                    numero_cnj=cnj,
                    tribunal=tribunal,
                    grau=inferir_grau_cnj(cnj),
                )
                for cnj in cnjs
            ]

        except Exception as e:
            logger.debug("PJe %s Playwright JSF: erro geral: %s", tribunal, e)
            return []
        finally:
            if browser:
                await browser.close()
            try:
                await pw.stop()
            except Exception:
                pass

    @staticmethod
    def _get_playwright_client():
        """Retorna cliente Playwright se disponível, ou None."""
        try:
            from playwright.async_api import async_playwright
            return True
        except ImportError:
            return None

    # ------------------------------------------------------------------
    # BUSCA POR OAB EM MÚLTIPLOS TRIBUNAIS
    # ------------------------------------------------------------------

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        tribunais: Optional[list[str]] = None,
        tamanho: int = 100,
        max_concorrentes: int = 20,
        cpf_advogado: Optional[str] = None,
    ) -> list[ProcessoCompleto]:
        """
        Busca em todos os tribunais PJe em paralelo com semáforo.
        """
        alvos = tribunais or TODOS_TRIBUNAIS_PJE
        semaphore = asyncio.Semaphore(max_concorrentes)

        async def consultar_tribunal(tribunal: str) -> list[ProcessoCompleto]:
            if tribunal not in PJE_URLS:
                return []
            async with semaphore:
                try:
                    return await asyncio.wait_for(
                        self.buscar_por_oab_tribunal(
                            tribunal=tribunal,
                            numero_oab=numero_oab,
                            uf_oab=uf_oab,
                            tamanho=tamanho,
                            cpf_advogado=cpf_advogado
                        ),
                        timeout=20.0
                    )
                except asyncio.TimeoutError:
                    logger.debug("PJe %s: timeout na busca paralela OAB %s", tribunal, numero_oab)
                    return []
                except Exception as e:
                    logger.debug("PJe %s: erro na busca paralela OAB %s: %s", tribunal, numero_oab, e)
                    return []

        tarefas = [consultar_tribunal(t) for t in alvos]
        resultados_gather = await asyncio.gather(*tarefas)
        
        # Achatar lista de listas
        resultados: list[ProcessoCompleto] = []
        for lista in resultados_gather:
            resultados.extend(lista)
        
        if resultados:
            logger.info("PJe: %d processos totais para OAB %s em %d sistemas", len(resultados), numero_oab, len(alvos))
        
        return resultados

    # ------------------------------------------------------------------
    # BUSCA POR CNJ
    # ------------------------------------------------------------------

    async def buscar_processo(
        self,
        numero_cnj: str,
        tribunal: str,
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        base = PJE_URLS.get(tribunal.lower())
        if not base:
            return None

        url = f"{base}/api/v1/processo/dadosbasicos/{numero_cnj}"
        try:
            resp = await self._get(url)
            if resp.status_code == 200:
                return self._parse_detalhe_api(resp.json(), numero_cnj, tribunal)
        except Exception as e:
            logger.debug("PJe %s: API detalhe falhou para %s: %s", tribunal, numero_cnj, e)

        # Fallback Firecrawl: se a API falhar, tenta raspar a página de consulta pública
        from src.crawlers.firecrawl_client import get_firecrawl_client
        fc = get_firecrawl_client()
        if fc:
            try:
                # URL de consulta pública para detalhe de processo no PJe (variação comum)
                detail_url = f"{base}/consultaPublica/DetalheProcessoConsultaPublica/listView.seam?numeroProcesso={numero_cnj}"
                html_fc = await fc.scrape_html(detail_url)
                if html_fc:
                    logger.info("PJe %s: HTML do detalhe obtido via Firecrawl para %s", tribunal, numero_cnj)
                    processo = self._parse_detalhe_html(html_fc, numero_cnj, tribunal)
                    if processo:
                        return processo
            except Exception as e:
                logger.debug("PJe %s: Firecrawl falhou para detalhe %s: %s", tribunal, numero_cnj, e)

        return None

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    def _parse_detalhe_html(self, html: str, numero_cnj: str, tribunal: str) -> Optional[ProcessoCompleto]:
        """
        Parse do HTML de detalhe de processo do PJe (fallback via Firecrawl).

        O HTML do PJe contém seções bem definidas:
        - #dadosBasicos ou table.dados-processo
        - #partes ou table.partes
        - #movimentacoes ou table.movimentacoes
        """
        soup = BeautifulSoup(html, "html.parser")

        comarca = ""
        vara = ""
        classe = ""
        distribuicao: Optional[datetime] = None
        valor: Optional[float] = None
        situacao = ""
        grau = ""

        # ── Dados básicos ────────────────────────────────────────────
        for tabela in soup.find_all(["table", "div"], class_=re.compile(r"dados|basico|processo", re.I)):
            for linha in tabela.find_all(["tr", "li", "div"]):
                texto = linha.get_text(" ", strip=True)
                if "Comarca" in texto or "Foro" in texto:
                    m = re.search(r"(?:Comarca|Foro)[^:]*:?\s*[:\-]?\s*([^\n\r]+)", texto)
                    if m:
                        comarca = m.group(1).strip()
                elif "Vara" in texto or "Órgão" in texto:
                    m = re.search(r"(?:Vara|Órgão)[^:]*:?\s*[:\-]?\s*([^\n\r]+)", texto)
                    if m:
                        vara = m.group(1).strip()
                elif "Classe" in texto:
                    m = re.search(r"Classe[^:]*:?\s*[:\-]?\s*([^\n\r]+)", texto)
                    if m:
                        classe = m.group(1).strip()
                elif "Distribuição" in texto or "Data" in texto:
                    m = re.search(r"(\d{2}/\d{2}/\d{4})", texto)
                    if m:
                        try:
                            distribuicao = datetime.strptime(m.group(1), "%d/%m/%Y")
                        except ValueError:
                            pass
                elif "Valor" in texto:
                    m = re.search(r"[R$]\s*([\d\.,]+)", texto)
                    if m:
                        try:
                            valor = float(m.group(1).replace(".", "").replace(",", "."))
                        except ValueError:
                            pass
                elif "Situação" in texto or "Status" in texto:
                    m = re.search(r"(?:Situação|Status)[^:]*:?\s*[:\-]?\s*([^\n\r]+)", texto)
                    if m:
                        situacao = m.group(1).strip()

        # ── Partes (polos ativo/passivo) ─────────────────────────────
        partes: list[ParteProcesso] = []
        polo_atual = "OUTROS"
        for tabela in soup.find_all(["table", "div"], class_=re.compile(r"parte|polo", re.I)):
            texto_tabela = tabela.get_text(" ", strip=True).upper()
            if "ATIVO" in texto_tabela:
                polo_atual = "ATIVO"
            elif "PASSIVO" in texto_tabela:
                polo_atual = "PASSIVO"
            for linha in tabela.find_all(["tr", "li", "div"]):
                cells = linha.find_all(["td", "span", "div"])
                if len(cells) < 2:
                    continue
                cell_texts = [c.get_text(strip=True) for c in cells]
                joined = " | ".join(cell_texts)

                # Identifica advogado
                if "ADVOGADO" in joined.upper():
                    nome_adv = cell_texts[-1] if cell_texts else ""
                    oab_m = re.search(r"(\d{6,7}[A-Z]{2})", joined, re.I)
                    partes.append(ParteProcesso(
                        nome=nome_adv.upper(),
                        tipo_parte="ADVOGADO",
                        polo=polo_atual,
                        oab=oab_m.group(0) if oab_m else None,
                    ))
                # Identifica parte (não advogado)
                elif any(t in joined.upper() for t in ["REQUERENTE", "AUTOR", "EXEQUENTE", "RECLAMANTE"]):
                    nome = cell_texts[-1] if cell_texts else ""
                    if nome and len(nome) > 3:
                        partes.append(ParteProcesso(nome=nome.upper(), tipo_parte="REQUERENTE", polo="ATIVO"))
                elif any(t in joined.upper() for t in ["REQUERIDO", "RÉU", "RÉ", "EXECUTADO", "RECLAMADO"]):
                    nome = cell_texts[-1] if cell_texts else ""
                    if nome and len(nome) > 3:
                        partes.append(ParteProcesso(nome=nome.upper(), tipo_parte="REQUERIDO", polo="PASSIVO"))

        # ── Movimentações ─────────────────────────────────────────────
        movimentacoes: list[MovimentacaoProcesso] = []
        for tabela in soup.find_all(["table", "div"], class_=re.compile(r"moviment", re.I)):
            for linha in tabela.find_all(["tr", "li"]):
                cells = linha.find_all(["td", "span"])
                if len(cells) >= 2:
                    data_texto = cells[0].get_text(strip=True)
                    desc_texto = " ".join(c.get_text(strip=True) for c in cells[1:])
                    data_mov = self._parse_data_brasileira(data_texto)
                    if desc_texto and data_mov:
                        movimentacoes.append(MovimentacaoProcesso(
                            data_movimentacao=data_mov,
                            descricao=desc_texto,
                            tipo="",
                            impacto="",
                        ))

        return ProcessoCompleto(
            numero_cnj=numero_cnj,
            tribunal=tribunal,
            comarca=comarca,
            grau=grau,
            vara=vara,
            classe_processual=classe,
            data_distribuicao=distribuicao,
            valor_causa=valor,
            situacao=situacao,
            partes=partes,
            movimentacoes=movimentacoes,
        )

    def _parse_data_brasileira(self, texto: str) -> Optional[datetime]:
        """Converte data DD/MM/YYYY ou DD/MM/YYYY HH:MM."""
        if not texto:
            return None
        texto = texto.strip()[:16]
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
            try:
                return datetime.strptime(texto[:len(fmt.replace(" ", ""))], fmt)
            except ValueError:
                pass
        return None

    def _parse_lista_api(self, data: Any, tribunal: str) -> list[ProcessoCompleto]:
        """
        Parse da resposta da API REST /advogado/{oab}/processos.

        A API PJe pode retornar JSON em vários formatos dependendo do tribunal:
          - lista direta: [{...}, ...]
          - {"content": [...]}            (Spring Page)
          - {"processos": [...]}
          - {"data": [...]}
          - {"records": [...]}
          - {"lista": [...]}
          - {"totalElements": N, "content": [...]}
        """
        processos = []

        # Normaliza para lista de itens
        if isinstance(data, list):
            itens = data
        else:
            itens = []
            for chave in ("content", "processos", "data", "records",
                          "lista", "itens", "result", "results"):
                v = data.get(chave) if isinstance(data, dict) else None
                if isinstance(v, list):
                    itens = v
                    break
            if not itens and isinstance(data, dict):
                # Loga chaves disponíveis para diagnóstico
                total = data.get("totalElements", data.get("total", data.get("count")))
                if total is not None:
                    logger.info("PJe %s: API retornou totalElements=%s mas nenhuma lista reconhecida."
                                " Chaves: %s", tribunal, total, list(data.keys()))
                elif data:
                    logger.debug("PJe %s: JSON sem lista reconhecida. Chaves: %s",
                                 tribunal, list(data.keys()))

        for item in itens:
            numero = (
                item.get("numeroProcesso")
                or item.get("numero")
                or item.get("numeroDoProcesso", "")
            )
            if not numero:
                continue

            partes = self._extrair_partes_api(item)
            movs = self._extrair_movs_api(item)

            processos.append(ProcessoCompleto(
                numero_cnj=numero,
                tribunal=tribunal,
                vara=self._campo(item, "orgaoJulgador", "nomeOrgao"),
                classe_processual=self._campo(item, "classeProcessual", "descricao"),
                data_distribuicao=self._parse_data(item.get("dataAjuizamento", "")),
                partes=partes,
                movimentacoes=movs,
                dados_brutos=item,
            ))

        return processos

    def _parse_lista_html(self, html: str, tribunal: str) -> list[ProcessoCompleto]:
        """Extrai números CNJ do HTML de lista do PJe."""
        padrao = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
        numeros = list(dict.fromkeys(re.findall(padrao, html)))
        # Filtra placeholders de máscara JS (ex: 9999999-99.9999.9.99.9999)
        numeros = [n for n in numeros if not re.fullmatch(r"9+[-.]9+[-.]9+[-.]9[-.]9+[-.]9+", n)]
        return [ProcessoCompleto(numero_cnj=n, tribunal=tribunal) for n in numeros]

    def _parse_detalhe_api(self, data: dict, numero_cnj: str, tribunal: str) -> ProcessoCompleto:
        processo = data.get("processo") or data
        return ProcessoCompleto(
            numero_cnj=numero_cnj,
            tribunal=tribunal,
            vara=self._campo(processo, "orgaoJulgador", "nomeOrgao"),
            classe_processual=self._campo(processo, "classeProcessual", "descricao"),
            data_distribuicao=self._parse_data(processo.get("dataAjuizamento", "")),
            partes=self._extrair_partes_api(processo),
            movimentacoes=self._extrair_movs_api(processo),
            dados_brutos=data,
        )

    def _extrair_partes_api(self, data: dict) -> list[ParteProcesso]:
        partes: list[ParteProcesso] = []
        for polo_raw in data.get("polo", []):
            if not isinstance(polo_raw, dict):
                continue
            polo_letra = polo_raw.get("polo", "").upper()
            polo_val = "ATIVO" if polo_letra in ("A", "ATIVO") else (
                "PASSIVO" if polo_letra in ("P", "PASSIVO") else "OUTROS"
            )
            for p in polo_raw.get("parte", []):
                if not isinstance(p, dict):
                    continue
                nome = p.get("pessoa", {}).get("nome", "") if isinstance(p.get("pessoa"), dict) else ""
                nome = nome or p.get("nome", "")
                tipo = p.get("tipoParte", {}).get("descricao", "PARTE").upper() if isinstance(p.get("tipoParte"), dict) else "PARTE"
                if nome:
                    partes.append(ParteProcesso(nome=nome.upper(), tipo_parte=tipo, polo=polo_val))

                advogados = p.get("advogado", [])
                if isinstance(advogados, list):
                    for adv in advogados:
                        if not isinstance(adv, dict):
                            continue
                        nome_adv = adv.get("nome", "")
                        oab_num = adv.get("numeroOAB", "")
                        uf_adv = adv.get("ufOAB", "")
                        if nome_adv:
                            partes.append(ParteProcesso(
                                nome=nome_adv.upper(),
                                tipo_parte="ADVOGADO",
                                polo=polo_val,
                                oab=f"{oab_num}{uf_adv}" if oab_num else None,
                            ))
        return partes

    def _extrair_movs_api(self, data: dict) -> list[MovimentacaoProcesso]:
        movs: list[MovimentacaoProcesso] = []
        for m in data.get("movimento", []):
            if not isinstance(m, dict):
                continue
            data_str = m.get("dataHora", "")[:10]
            desc = (
                m.get("movimentoNacional", {}).get("descricao") if isinstance(m.get("movimentoNacional"), dict) else ""
            )
            desc = desc or m.get("complemento", "") or m.get("descricao", "")
            codigo = m.get("movimentoNacional", {}).get("codigoNacional") if isinstance(m.get("movimentoNacional"), dict) else None
            d = self._parse_data(data_str)
            if d and desc:
                movs.append(MovimentacaoProcesso(
                    data_movimentacao=d,
                    descricao=desc,
                    codigo_nacional=int(codigo) if codigo else None,
                ))
        return sorted(movs, key=lambda x: x.data_movimentacao, reverse=True)

    def _campo(self, obj: dict, *keys: str) -> Optional[str]:
        for k in keys:
            obj = obj.get(k, {}) if isinstance(obj, dict) else {}
        return str(obj) if obj and not isinstance(obj, dict) else None

    def _parse_data(self, s: str) -> Optional[date]:
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
