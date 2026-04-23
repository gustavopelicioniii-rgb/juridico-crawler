"""
Crawler TJSP via eSaj — busca por OAB e por número CNJ.
Sistema: https://esaj.tjsp.jus.br

Suporta:
- Busca de todos os processos de um advogado por OAB (cbPesquisa=NUMOAB)
- Paginação via conversationId (necessário para páginas 2+)
- Fetch de detalhe completo (partes + movimentações) para cada processo encontrado
- Busca por número CNJ direto
"""

import asyncio
import structlog
import re
from typing import Any, Optional
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import (
    MovimentacaoProcesso,
    ParteProcesso,
    ProcessoCompleto,
    inferir_grau_cnj,
)

logger = structlog.get_logger(__name__)

ESAJ_BASE = "https://esaj.tjsp.jus.br"


class TJSPCrawler(BaseCrawler):

    def __init__(
        self,
        requests_per_minute=None,
        max_retries=None,
        timeout: float = 30.0,
        esaj_base: str = ESAJ_BASE,
        tribunal_id: str = "tjsp",
        proxy_pool=None,
        captcha_solver=None,
        verify_ssl: bool = True,
    ) -> None:
        super().__init__(requests_per_minute, max_retries, timeout,
                         proxy_pool=proxy_pool, captcha_solver=captcha_solver,
                         verify_ssl=verify_ssl)
        self.esaj_base = esaj_base
        self.tribunal_id = tribunal_id

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Referer": f"{self.esaj_base}/cpopg/open.do",
        }

    async def __aenter__(self) -> "TJSPCrawler":
        await super().__aenter__()
        # O eSaj exige que a sessão seja iniciada visitando open.do para
        # que o servidor emita o cookie JSESSIONID. Sem ele, show.do retorna
        # "Processo não encontrado" mesmo para processos válidos.
        self._session_ok = False
        try:
            await self._get(f"{self.esaj_base}/cpopg/open.do")
            self._session_ok = True
            logger.debug("%s: sessão inicializada (JSESSIONID obtido via open.do)", self.tribunal_id.upper())
        except Exception as e:
            logger.warning(
                "%s: falha ao inicializar sessão em open.do (%s: %s) — TJ inacessível",
                self.tribunal_id.upper(), type(e).__name__, e,
            )
        return self

    # ------------------------------------------------------------------
    # BUSCA POR OAB
    # ------------------------------------------------------------------

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str = "SP",
        paginas: int = 10,
        max_detalhes_concorrentes: int = 3,
    ) -> list[ProcessoCompleto]:
        """
        Busca todos os processos de um advogado no TJSP pelo número OAB.

        Fase 1: percorre lista paginada do eSaj coletando {cnj, codigo, foro}.
                - Usa conversationId para paginar corretamente (sem ele cada
                  requisição retorna sempre a primeira página).
        Fase 2: busca detalhe de cada processo único (partes + movimentações)
                com concorrência limitada pelo semáforo.

        Args:
            numero_oab: Número sem UF (ex: "361329")
            uf_oab: UF da OAB (ex: "SP")
            paginas: Máximo de páginas a percorrer (25 proc/pág)
            max_detalhes_concorrentes: Nº de fetches de detalhe em paralelo

        Returns:
            Lista de ProcessoCompleto com partes e movimentações preenchidas
        """
        # Se open.do falhou no __aenter__, o TJ está inacessível — não tenta Firecrawl.
        if not getattr(self, "_session_ok", True):
            logger.debug(
                "%s OAB %s/%s: sessão não inicializada (TJ inacessível) — retornando []",
                self.tribunal_id.upper(), numero_oab, uf_oab,
            )
            return []

        # ---- Fase 1: coletar metadados da lista -------------------------
        processos_meta: dict[str, dict] = {}  # cnj -> {codigo, foro}
        conversation_id: str = ""
        pagina = 1

        while pagina <= paginas:
            logger.info(
                "TJSP OAB %s/%s — página %d/%d (conv=%s)",
                numero_oab, uf_oab, pagina, paginas, conversation_id or "nova",
            )

            # Definir URL e parâmetros
            if pagina == 1:
                url_consulta = f"{self.esaj_base}/cpopg/search.do"
                # Parâmetros mínimos observados no navegador que retornam 39 resultados
                params: dict[str, str] = {
                    "cbPesquisa": "NUMOAB",
                    "dadosConsulta.valorConsulta": numero_oab,
                    "cdForo": "-1",
                    "paginaConsulta": "1",
                }
                current_referer = f"{self.esaj_base}/cpopg/open.do"
            else:
                url_consulta = f"{self.esaj_base}/cpopg/trocarPagina.do"
                params: dict[str, str] = {
                    "paginaConsulta": str(pagina),
                    "cbPesquisa": "NUMOAB",
                    "dadosConsulta.valorConsulta": numero_oab,
                    "cdForo": "-1",
                    "conversationId": conversation_id or "",
                }
                current_referer = f"{self.esaj_base}/cpopg/search.do"

            try:
                # O httpx.AsyncClient mantém os cookies se usarmos a mesma instância
                resp = await self._get(
                    url_consulta, 
                    params=params, 
                    headers={
                        "Referer": current_referer,
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    }
                )
                html = resp.text
                if "processo" not in html.lower() and "não existem informações" not in html.lower():
                    logger.warning("%s: Resposta inesperada na pág %d (possível bloqueio/captcha)", self.tribunal_id.upper(), pagina)
            except Exception as e:
                logger.error("%s: Erro crítico na pág %d para OAB %s: %s", self.tribunal_id.upper(), pagina, numero_oab, e)
                html = ""

            # Fallback Firecrawl se a resposta direta não parecer correta ou falhar
            if not html or "captcha" in html.lower() or "não existem informações" not in html and "processo" not in html.lower():
                from src.crawlers.firecrawl_client import get_firecrawl_client
                fc = get_firecrawl_client()
                if fc:
                    try:
                        from urllib.parse import urlencode
                        full_url = f"{self.esaj_base}/cpopg/search.do?{urlencode(params)}"
                        html_fc = await fc.scrape_html(full_url)
                        if html_fc and ("processo" in html_fc.lower() or "não existem informações" in html_fc.lower()):
                            html = html_fc
                            logger.info("%s OAB %s: página %d obtida via Firecrawl", self.tribunal_id.upper(), numero_oab, pagina)
                    except Exception as ef:
                        logger.debug("%s OAB %s: Firecrawl falhou: %s", self.tribunal_id.upper(), numero_oab, ef)

            if not html:
                break

            # Extrair conversationId da primeira resposta
            if pagina == 1 and not conversation_id:
                conversation_id = self._extrair_conversation_id(html)
                logger.debug("TJSP: conversationId extraído: %s", conversation_id)

            if "Não existem informações" in html or "nenhum processo" in html.lower() or "não existem dados" in html.lower():
                break

            novos = self._extrair_meta_lista(html)
            if not novos:
                break

            antes = len(processos_meta)
            for m in novos:
                if m["cnj"] not in processos_meta:
                    processos_meta[m["cnj"]] = m
            adicionados = len(processos_meta) - antes

            logger.info(
                "TJSP OAB %s: página %d → +%d novos (total: %d)",
                numero_oab, pagina, adicionados, len(processos_meta),
            )

            # Se não adicionou nenhum novo, paginação está repetindo — parar
            if adicionados == 0:
                logger.info("TJSP: nenhum processo novo na página %d — encerrando", pagina)
                break

            # Verificar se há próxima página
            tem_proxima = (
                "Próxima" in html
                or "próxima" in html.lower()
                or f'paginaAtual={pagina + 1}' in html
                or f'paginaConsulta={pagina + 1}' in html
                or ">Próximo<" in html
            )
            if not tem_proxima:
                break

            pagina += 1

        if not processos_meta:
            logger.warning(
                "TJSP OAB %s/%s: nenhum processo encontrado na lista", numero_oab, uf_oab
            )
            return []

        logger.info(
            "TJSP OAB %s/%s: %d processos únicos — buscando detalhes...",
            numero_oab, uf_oab, len(processos_meta),
        )

        # ---- Fase 2: buscar detalhe de cada processo -------------------
        semaforo = asyncio.Semaphore(max_detalhes_concorrentes)

        async def buscar_detalhe(meta: dict) -> ProcessoCompleto:
            async with semaforo:
                try:
                    return await self._buscar_detalhe_por_meta(meta)
                except Exception as e:
                    logger.warning("%s: detalhe %s falhou: %s", self.tribunal_id.upper(), meta["cnj"], e)
                    return ProcessoCompleto(numero_cnj=meta["cnj"], tribunal=self.tribunal_id)

        resultados = await asyncio.gather(
            *[buscar_detalhe(m) for m in processos_meta.values()],
        )

        validos = [r for r in resultados if r is not None]
        logger.info(
            "TJSP OAB %s/%s: %d processos com detalhes obtidos",
            numero_oab, uf_oab, len(validos),
        )
        return validos

    # ------------------------------------------------------------------
    # Extração da lista de resultados
    # ------------------------------------------------------------------

    def _extrair_meta_lista(self, html: str) -> list[dict]:
        """
        Extrai {cnj, codigo, foro} de cada processo na página de lista.
        Usa selectolax com fallback para regex.
        """
        try:
            from selectolax.parser import HTMLParser
        except ImportError:
            return self._extrair_meta_regex(html)

        tree = HTMLParser(html)
        metas: list[dict] = []
        padrao_cnj = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")

        # Links que apontam para o detalhe do processo
        for a in tree.css(
            "a[href*='cpopg/show.do'], a[href*='cpopg/open.do'], "
            "a[href*='show.do'], a[href*='open.do']"
        ):
            texto = a.text(strip=True)
            m_cnj = padrao_cnj.search(texto)
            if not m_cnj:
                continue

            cnj = m_cnj.group(0)
            href = a.attrs.get("href", "")
            codigo = self._extrair_param_url(href, "processo.codigo")
            foro = self._extrair_param_url(href, "processo.foro")

            if not foro:
                partes_num = self._extrair_partes_numero(cnj)
                foro = self._foro_para_tjsp(partes_num["origem"]) if partes_num else ""

            metas.append({"cnj": cnj, "codigo": codigo, "foro": foro})

        if not metas:
            return self._extrair_meta_regex(html)

        return metas

    def _extrair_meta_regex(self, html: str) -> list[dict]:
        """Fallback regex para extração de metadados da lista."""
        padrao_cnj = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"

        # Tenta extrair de href com processo.codigo no mesmo padrão
        patt = (
            r'href=["\']?([^"\'>\s]*cpopg/(?:show|open)\.do\?[^"\'>\s]*)["\']?[^>]*>\s*'
            r'(' + padrao_cnj + r')'
        )
        hrefs = re.findall(patt, html, re.IGNORECASE)

        if hrefs:
            metas = []
            for href, cnj in hrefs:
                codigo = self._extrair_param_url(href, "processo.codigo")
                foro = self._extrair_param_url(href, "processo.foro")
                if not foro:
                    partes_num = self._extrair_partes_numero(cnj)
                    foro = self._foro_para_tjsp(partes_num["origem"]) if partes_num else ""
                metas.append({"cnj": cnj, "codigo": codigo, "foro": foro})
            return metas

        # Último recurso: só CNJs (sem código e foro do href)
        numeros = list(dict.fromkeys(re.findall(padrao_cnj, html)))
        result = []
        for n in numeros:
            partes_num = self._extrair_partes_numero(n)
            result.append({
                "cnj": n,
                "codigo": "",
                "foro": self._foro_para_tjsp(partes_num["origem"]) if partes_num else "",
            })
        return result

    # ------------------------------------------------------------------
    # Busca de detalhe individual
    # ------------------------------------------------------------------

    async def _buscar_detalhe_por_meta(self, meta: dict) -> ProcessoCompleto:
        """Busca a página de detalhe usando processo.codigo + processo.foro."""
        url = f"{self.esaj_base}/cpopg/show.do"

        # processo.codigo (código interno eSaj) identifica o processo de forma inequívoca.
        # Sem ele, usa processo.numero (CNJ). Ambos precisam de processo.foro.
        params: dict[str, str] = {}
        if meta.get("codigo"):
            params["processo.codigo"] = meta["codigo"]
        else:
            params["processo.numero"] = meta["cnj"]

        if meta.get("foro"):
            params["processo.foro"] = self._foro_para_tjsp(meta["foro"])
        else:
            partes_num = self._extrair_partes_numero(meta["cnj"])
            if partes_num:
                params["processo.foro"] = self._foro_para_tjsp(partes_num["origem"])

        logger.debug("%s detalhe params: %s", self.tribunal_id.upper(), params)

        try:
            resp = await self._get(url, params=params)
        except Exception as e:
            logger.error("%s: erro ao buscar detalhe %s: %s", self.tribunal_id.upper(), meta["cnj"], e)
            raise

        texto = resp.text
        logger.debug(
            "%s detalhe %s: status=%s, tamanho=%d, url_final=%s",
            self.tribunal_id.upper(), meta["cnj"], resp.status_code, len(texto), str(resp.url)[:120],
        )
        if "Processo não encontrado" in texto or "processo não existe" in texto.lower():
            logger.warning("%s %s: 'Processo não encontrado' — params=%s", self.tribunal_id.upper(), meta["cnj"], params)
            return ProcessoCompleto(numero_cnj=meta["cnj"], tribunal=self.tribunal_id)

        resultado = self._parse_detalhe(texto, meta["cnj"])

        # Fallback Firecrawl: se 0 partes, tenta scraping com JS para desbloqueio
        if not resultado.partes:
            from src.crawlers.firecrawl_client import get_firecrawl_client
            fc = get_firecrawl_client()
            if fc:
                try:
                    html_fc = await fc.scrape_html(str(resp.url))
                    if html_fc:
                        resultado_fc = self._parse_detalhe(html_fc, meta["cnj"])
                        if resultado_fc.partes:
                            logger.info(
                                "%s %s: partes obtidas via Firecrawl (%d)",
                                self.tribunal_id.upper(), meta["cnj"], len(resultado_fc.partes),
                            )
                            resultado.partes = resultado_fc.partes
                except Exception as e:
                    logger.debug("%s: Firecrawl falhou para %s: %s", self.tribunal_id.upper(), meta["cnj"], e)

        return resultado

    # ------------------------------------------------------------------
    # BUSCA POR NÚMERO CNJ (interface pública, compatível com BaseCrawler)
    # ------------------------------------------------------------------

    async def buscar_processo(
        self,
        numero_cnj: str,
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        """Busca um processo específico e retorna com todos os detalhes."""
        partes_num = self._extrair_partes_numero(numero_cnj)
        if not partes_num:
            return None

        meta = {
            "cnj": numero_cnj,
            "codigo": kwargs.get("codigo", ""),
            "foro": self._foro_para_tjsp(partes_num["origem"]),
        }
        return await self._buscar_detalhe_por_meta(meta)

    # ------------------------------------------------------------------
    # Parser do HTML de detalhe
    # ------------------------------------------------------------------

    def _parse_detalhe(self, html: str, numero_cnj: str) -> ProcessoCompleto:
        """
        Parse completo do HTML de detalhe do processo no eSaj.

        Estrutura real do TJSP eSaj (cpopg/show.do):
        - Partes: <table id="tablePartesPrincipais"> (ou tableTodasPartes)
            <tr>
              <td class="label">Autor:</td>
              <td>
                <span class="nomeParteEAdvogado">NOME DA PARTE</span>
                <span class="nomeParteEAdvogado">Advogado: NOME - OAB/SP 361329</span>
              </td>
            </tr>
        - Movimentos: <table id="tabelaTodasMovimentacoes"> ou #tabelaUltimasMovimentacoes
        """
        try:
            from selectolax.parser import HTMLParser
            tree = HTMLParser(html)

            def txt(sel: str) -> Optional[str]:
                n = tree.css_first(sel)
                return n.text(strip=True) if n else None

            # ── Campos básicos ─────────────────────────────────────────
            classe   = txt("#classeProcesso") or txt(".classeProcesso")
            assunto  = txt("#assuntoProcesso") or txt(".assuntoProcesso") or txt("#assuntoPrincipalProcesso")
            vara     = txt("#varaProcesso") or txt(".varaProcesso") or txt("#juizoProcesso")
            comarca  = txt("#foroProcesso") or txt(".foroProcesso") or txt("#comarcaProcesso") or txt(".comarcaProcesso")
            situacao = txt("#situacaoProcesso")  or txt(".situacaoProcesso")

            # Valor da causa
            valor_causa = None
            valor_raw = txt("#valorAcaoProcesso") or txt(".valorAcaoProcesso")
            if valor_raw:
                numstr = re.sub(r"[^\d,]", "", valor_raw).replace(",", ".")
                try:
                    valor_causa = Decimal(numstr)
                except (InvalidOperation, ValueError):
                    logger.debug("TJSP: valor da causa inválido '%s'", valor_raw)

            # Data distribuição
            data_dist = None
            data_raw = txt("#dataHoraDistribuicaoProcesso") or ""
            m = re.search(r"(\d{2}/\d{2}/\d{4})", data_raw)
            if m:
                try:
                    data_dist = datetime.strptime(m.group(1), "%d/%m/%Y").date()
                except ValueError:
                    pass

            # ── PARTES — estrutura real do eSAJ ────────────────────────
            # Versão nova (mais comum):
            # <table id="tablePartesPrincipais">
            #   <tr>
            #     <td class="label">Autor:</td>
            #     <td class="nomeParteEAdvogado">
            #       NomeDaParte
            #       <br/>
            #       <span class="mensagemExibindo">Advogada:&nbsp;</span>
            #       NomeDoAdvogado
            #     </td>
            #   </tr>
            # </table>
            # Versão antiga (alguns foros):
            # <td>
            #   <span class="nomeParteEAdvogado">NOME DA PARTE</span>
            #   <span class="nomeParteEAdvogado">Advogado: NOME - OAB/SP 123456</span>
            # </td>
            partes: list[ParteProcesso] = []

            parties_table = (
                tree.css_first("#tablePartesPrincipal")
                or tree.css_first("#tablePartesPrincipais")
                or tree.css_first("#tableTodasPartes")
                or tree.css_first("table[id*='Partes']")
            )

            if parties_table:
                current_tipo: Optional[str] = None
                for row in parties_table.css("tr"):
                    # Detectar label do tipo de parte (ex: "Autor:", "Réu:", "Advogado:")
                    label_td = row.css_first("td.label")
                    if not label_td:
                        # fallback: td cujo conteúdo termina com ":"
                        for td in row.css("td"):
                            t = td.text(strip=True)
                            if t.endswith(":") and len(t) < 60 and "\n" not in t:
                                label_td = td
                                break

                    if label_td:
                        raw_label = re.sub(r"[\s\xa0\u00a0]+", " ", label_td.text()).strip().rstrip(":")
                        if raw_label:
                            current_tipo = raw_label.upper()

                    # Extrair nomes — suporta TANTO td.nomeParteEAdvogado QUANTO span.nomeParteEAdvogado
                    # Estrutura real do eSAJ:
                    #   <td class="nomeParteEAdvogado">
                    #     NomeDaParte
                    #     <br/>
                    #     <span class="mensagemExibindo">Advogada:&nbsp;</span>
                    #     NomeDoAdvogado
                    #   </td>
                    # OU (versão mais antiga):
                    #   <span class="nomeParteEAdvogado">NOME</span>
                    #   <span class="nomeParteEAdvogado">Advogado: NOME - OAB/SP 123456</span>
                    for node in row.css("td.nomeParteEAdvogado, span.nomeParteEAdvogado"):
                        polo = self._polo_de_tipo(current_tipo or "")
                        partes.extend(self._extrair_partes_de_node(node, polo, current_tipo))

            # ── Fallback A: varrer QUALQUER tr do documento que tenha td/span.nomeParteEAdvogado
            if not partes:
                current_tipo_fb: Optional[str] = None
                for row in tree.css("tr"):
                    nos_na_linha = row.css("td.nomeParteEAdvogado, span.nomeParteEAdvogado")
                    if not nos_na_linha:
                        # Fallback NUCLEAR: se não tem a classe, mas a primeira TD parece um rótulo de parte
                        cells = row.css("td")
                        if len(cells) >= 2:
                            primeiro_td = re.sub(r"[\s\xa0\u00a0]+", " ", cells[0].text()).strip()
                            if primeiro_td.rstrip(":").upper() in ["AUTOR", "RÉU", "REQUERENTE", "REQUERIDO", "AUTO", "RÉ"]:
                                current_tipo_fb = primeiro_td.rstrip(":").upper()
                                partes.extend(self._extrair_partes_de_node(cells[1], self._polo_de_tipo(current_tipo_fb), current_tipo_fb))
                                continue
                        continue
                    
                    cells = row.css("td")
                    if cells:
                        primeiro_td = re.sub(r"[\s\xa0\u00a0]+", " ", cells[0].text()).strip()
                        if (
                            primeiro_td
                            and len(primeiro_td) < 60
                            and not re.search(r"\d{2}/\d{2}/\d{4}", primeiro_td)
                            and not re.search(r"^\d", primeiro_td)
                        ):
                            current_tipo_fb = primeiro_td.rstrip(":").rstrip("\xa0").strip().upper() or current_tipo_fb

                    for node in nos_na_linha:
                        polo = self._polo_de_tipo(current_tipo_fb or "")
                        partes.extend(self._extrair_partes_de_node(node, polo, current_tipo_fb))

            # ── Fallback B: .tipoParticipacao + .nomeParticipante (foros alternativos)
            if not partes:
                for row in tree.css("tr"):
                    tipo_node = row.css_first(".tipoParticipacao, td.tipoParticipacao")
                    nome_node = row.css_first(".nomeParticipante, td.nomeParticipante")
                    if not (tipo_node and nome_node):
                        continue
                    tipo = tipo_node.text(strip=True).upper().rstrip(":")
                    nome = nome_node.text(strip=True)
                    if not nome:
                        continue
                    polo = self._polo_de_tipo(tipo)
                    oab = None
                    oab_m = re.search(r"OAB[/\s]*(\w{2})\s*(\d+)", nome, re.IGNORECASE)
                    if oab_m:
                        oab = f"{oab_m.group(2)}{oab_m.group(1).upper()}"
                        nome = re.sub(r"\s*[-–]\s*OAB[/\s]*\w{2}\s*\d+", "", nome, flags=re.IGNORECASE).strip()
                    partes.append(ParteProcesso(nome=nome.upper(), tipo_parte=tipo, polo=polo, oab=oab))

            # ── Fallback C: texto puro — regex no HTML bruto
            # Última linha de defesa: procura padrão "Papel:\nNome" no texto extraído
            if not partes:
                partes = self._parse_partes_texto_puro(html, numero_cnj)

            if partes:
                logger.info("TJSP %s: %d parte(s) extraída(s)", numero_cnj, len(partes))
            else:
                logger.warning(
                    "TJSP %s: nenhuma parte encontrada — verifique /debug/tjsp/%s",
                    numero_cnj, numero_cnj,
                )

            # ── MOVIMENTAÇÕES ─────────────────────────────────────────
            # Tabela dedicada: #tabelaTodasMovimentacoes ou #tabelaUltimasMovimentacoes
            movs: list[MovimentacaoProcesso] = []

            movs_table = (
                tree.css_first("#tabelaTodasMovimentacoes")
                or tree.css_first("#tabelaUltimasMovimentacoes")
                or tree.css_first("table[id*='Movimentacoes']")
                or tree.css_first("table[id*='Movimentacao']")
            )
            target_rows = (
                movs_table.css("tr")
                if movs_table
                else tree.css("tr.fundoClaro, tr.fundoEscuro")
            )

            for row in target_rows:
                cells = row.css("td")
                if len(cells) < 3:
                    continue
                data_cell = cells[0].text(strip=True)
                desc_cell = cells[2].text(strip=True)
                m2 = re.match(r"(\d{2}/\d{2}/\d{4})", data_cell)
                if m2 and desc_cell:
                    try:
                        d = datetime.strptime(m2.group(1), "%d/%m/%Y").date()
                        movs.append(MovimentacaoProcesso(data_movimentacao=d, descricao=desc_cell[:500]))
                    except ValueError:
                        continue

            # Normalização Inteligente de Status
            situacao_final = self._normalizar_situacao(situacao, movs)

            return ProcessoCompleto(
                numero_cnj=numero_cnj,
                tribunal=self.tribunal_id,
                grau=inferir_grau_cnj(numero_cnj),
                vara=vara,
                comarca=comarca,
                classe_processual=classe,
                assunto=assunto,
                valor_causa=valor_causa,
                data_distribuicao=data_dist,
                situacao=situacao_final,
                partes=partes,
                movimentacoes=sorted(movs, key=lambda x: x.data_movimentacao, reverse=True),
            )

        except Exception as e:
            logger.error("%s: erro ao parsear detalhe de %s: %s", self.tribunal_id.upper(), numero_cnj, e)
            return ProcessoCompleto(numero_cnj=numero_cnj, tribunal=self.tribunal_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalizar_situacao(self, situacao_raw: Optional[str], movs: list[MovimentacaoProcesso]) -> str:
        """
        Normaliza o status do processo com base no cabeçalho e nas últimas movimentações.
        Prioriza manter o advogado alerta (Arquivado Provisoriamente = Em Andamento).
        """
        status = (situacao_raw or "").upper()
        
        # Se o tribunal diz "Conclusão", é apenas envio ao juiz (ativo)
        # Atenção: "concluída" costuma se referir a "Comunicação concluída" ou "Conclusão para despacho"
        if any(t in status for t in ["CONCLUSAO", "CONCLUSOS", "CONCLUIDA", "CONCLUÍDA", "CONCLUIDO", "CONCLUÍDO"]):
            # Se a string contém "AUTOS CONCLUSOS" ou "DESPACHO", é andamento
            if any(t in status for t in ["AUTOS", "DESPACHO", "JUIZ", "SENTENÇA", "SENTENCA", "DECISÃO", "DECISAO"]):
                return "EM ANDAMENTO"
            
            # Se for apenas a palavra isolada, checamos se não é um dos termos de fim
            termos_fim_absoluto = ["EXTINTO", "BAIXADO", "ENCERRADO", "ARQUIVADO DEFINITIVAMENTE", "ARQUIVAMENTO DEFINITIVO"]
            if not any(t in status for t in termos_fim_absoluto):
                return "EM ANDAMENTO"
        
        # Se o tribunal já diz que está extinto ou baixado no cabeçalho
        termos_concluidos = ["EXTINTO", "BAIXADO", "ENCERRADO", "ARQUIVADO DEFINITIVAMENTE"]
        if any(t in status for t in termos_concluidos):
            return "CONCLUÍDO"
            
        # Se não há status no cabeçalho, olhamos a última movimentação
        if not movs:
            return "EM ANDAMENTO"
            
        ultima_mov = movs[0].descricao.upper()
        
        # Termos que indicam fim real
        termos_fim_real = ["BAIXA DEFINITIVA", "TRANSITADO EM JULGADO", "PROCESSO EXTINTO", "ARQUIVAMENTO DEFINITIVO"]
        if any(t in ultima_mov for t in termos_fim_real):
            return "CONCLUÍDO"
            
        # Padrão é Em Andamento (inclusive para Arquivado Provisoriamente ou Suspenso)
        return "EM ANDAMENTO"

    def _parse_partes_texto_puro(self, html: str, numero_cnj: str) -> list[ParteProcesso]:
        """
        Fallback de último recurso: extrai partes do texto bruto do HTML.

        Busca blocos do tipo:
            Autor:\n    NOME DA PARTE\n    Advogado:   NOME - OAB/SP 361329
        usando apenas regex sobre o texto, sem depender de CSS.
        """
        # Converte HTML para texto simples preservando quebras de linha
        try:
            from selectolax.parser import HTMLParser
            texto = HTMLParser(html).text(separator="\n")
        except Exception:
            # Remove tags HTML e decodifica entidades básicas
            texto = re.sub(r"<[^>]+>", "\n", html)
            texto = texto.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")

        # Normaliza espaços múltiplos dentro de cada linha (preserva \n)
        linhas = [re.sub(r"[ \t\xa0]+", " ", l).strip() for l in texto.splitlines()]
        linhas = [l for l in linhas if l]  # remove vazias

        papeis = {
            "AUTOR", "AUTORA", "AUTORES", "AUTORAS",
            "RÉU", "RÉ", "RÉUS", "RÉS", "REU", "ROUS",
            "REQUERENTE", "REQUERENTES", "REQUERIDO", "REQUERIDOS",
            "EXEQUENTE", "EXEQUENTES", "EXECUTADO", "EXECUTADOS",
            "IMPETRANTE", "IMPETRADO", "RECLAMANTE", "RECLAMADO",
            "APELANTE", "APELADO", "EMBARGANTE", "EMBARGADO",
            "TERCEIRO INTERESSADO", "TERCEIRO", "INTERVENIENTE",
            "LITISCONSORTE", "ASSISTENTE",
        }

        partes: list[ParteProcesso] = []
        tipo_atual: Optional[str] = None

        for i, linha in enumerate(linhas):
            # Verifica se a linha é um label de papel processual (ex: "Autor:", "Réu:")
            candidato = linha.rstrip(":").strip().upper()
            # Labels de parte são curtos e sem vírgula — evita capturar texto de movimentações
            if (
                (candidato in papeis or any(candidato.startswith(p) for p in papeis))
                and len(candidato) < 40
                and "," not in candidato
            ):
                tipo_atual = candidato
                continue

            # Linha de advogado
            if re.match(r"^advogad[ao][:\s]", linha, re.IGNORECASE) and tipo_atual:
                nome_adv = re.sub(r"^advogad[ao][:\s]+", "", linha, flags=re.IGNORECASE).strip()
                oab_m = re.search(r"OAB[/\s]*([A-Z]{2})\s*(\d{3,8})", nome_adv, re.IGNORECASE)
                oab = None
                if oab_m:
                    oab = f"{oab_m.group(2)}{oab_m.group(1).upper()}"
                    nome_adv = re.sub(r"\s*[-–]\s*OAB[/\s]*[A-Z]{2}\s*\d+", "", nome_adv, flags=re.IGNORECASE).strip()
                polo = self._polo_de_tipo(tipo_atual)
                if nome_adv and len(nome_adv) > 2:
                    partes.append(ParteProcesso(nome=nome_adv.upper(), tipo_parte="ADVOGADO", polo=polo, oab=oab))
                continue

            # Linha com OAB incrustada (ex: "NOME - OAB/SP 361329")
            if tipo_atual and re.search(r"OAB[/\s]*[A-Z]{2}\s*\d{4,8}", linha, re.IGNORECASE):
                oab_m = re.search(r"OAB[/\s]*([A-Z]{2})\s*(\d{3,8})", linha, re.IGNORECASE)
                oab = None
                nome_adv = linha
                if oab_m:
                    oab = f"{oab_m.group(2)}{oab_m.group(1).upper()}"
                    nome_adv = re.sub(r"\s*[-–]\s*OAB[/\s]*[A-Z]{2}\s*\d+", "", linha, flags=re.IGNORECASE).strip()
                polo = self._polo_de_tipo(tipo_atual)
                if nome_adv and len(nome_adv) > 2:
                    partes.append(ParteProcesso(nome=nome_adv.upper(), tipo_parte="ADVOGADO", polo=polo, oab=oab))
                continue

            # Nome da parte: logo após o tipo, deve ser texto razoável (nome próprio)
            if tipo_atual and i > 0:
                # Heurística: linha com 2+ palavras, sem datas, não muito longa
                if (
                    re.match(r"^[A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜÑ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇÜÑa-záéíóúàâêôãõçüñ\s\.\-']+$", linha)
                    and len(linha) > 4
                    and len(linha) < 120
                    and not re.search(r"\d{2}/\d{2}/\d{4}", linha)
                    and " " in linha  # pelo menos 2 palavras
                ):
                    polo = self._polo_de_tipo(tipo_atual)
                    partes.append(ParteProcesso(nome=linha.upper(), tipo_parte=tipo_atual, polo=polo))
                    tipo_atual = None

        if partes:
            logger.info("TJSP %s: %d parte(s) por parsing de texto puro", numero_cnj, len(partes))
        return partes

    def _extrair_conversation_id(self, html: str) -> str:
        """
        Extrai o conversationId da resposta do eSaj.
        Necessário para paginar corretamente — sem ele cada página 2+ re-executa
        a busca retornando sempre os mesmos 25 resultados.
        """
        # hidden input
        m = re.search(r'name="conversationId"\s+value="([^"]+)"', html, re.IGNORECASE)
        if m:
            return m.group(1)
        # em query string de link
        m = re.search(r'[?&]conversationId=([^&"&\s<>]+)', html)
        if m:
            return m.group(1)
        return ""

    def _extrair_param_url(self, url: str, param: str) -> str:
        """Extrai um parâmetro de uma URL parcial."""
        m = re.search(rf"[?&]{re.escape(param)}=([^&\"']+)", url)
        return m.group(1) if m else ""

    def _normalizar_numero(self, texto: str) -> Optional[str]:
        m = re.search(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", texto)
        return m.group(0) if m else None

    def _extrair_data(self, texto: str) -> Optional[date]:
        m = re.search(r"(\d{2}/\d{2}/\d{4})", texto)
        if m:
            try:
                return datetime.strptime(m.group(1), "%d/%m/%Y").date()
            except ValueError:
                pass
        return None

    def _extrair_classe(self, texto: str) -> Optional[str]:
        padroes = [
            r"Procedimento\s+\w+[\w\s]+",
            r"Ação\s+[\w\s]+",
            r"Execução[\w\s]+",
            r"Cumprimento[\w\s]+",
        ]
        for p in padroes:
            m = re.search(p, texto, re.IGNORECASE)
            if m:
                return m.group(0).strip()[:200]
        return None

    def _extrair_comarca(self, texto: str) -> Optional[str]:
        m = re.search(r"(?:Comarca|Foro)\s+(?:de\s+)?([A-ZÀ-Ú][a-zà-ú\s]+)", texto)
        return m.group(1).strip() if m else None

    def _extrair_partes_de_node(
        self,
        node: "Any",
        polo: Optional[str],
        tipo_atual: Optional[str],
    ) -> list["ParteProcesso"]:
        """
        Extrai parte(s) e advogado(s) de um único nó td.nomeParteEAdvogado
        ou span.nomeParteEAdvogado.

        Suporta duas estruturas do eSAJ:

        Estrutura nova (td):
            <td class="nomeParteEAdvogado">
                NomeDaParte
                <br/>
                <span class="mensagemExibindo">Advogada:&nbsp;</span>
                NomeDoAdvogado
                &nbsp;
            </td>

        Estrutura antiga (span):
            <span class="nomeParteEAdvogado">NOME DA PARTE</span>
            <span class="nomeParteEAdvogado">Advogado: NOME - OAB/SP 123456</span>
        """
        resultado: list[ParteProcesso] = []
        tag = node.tag.lower() if hasattr(node, "tag") else ""

        if tag == "td":
            # --- Estrutura nova: td.nomeParteEAdvogado ---
            # Precisamos obter os nós filhos para separar nome da parte e advogado(s).
            # selectolax não expõe text nodes diretamente, então usamos o HTML interno
            # e dividimos pelo <br> e pelos spans mensagemExibindo.
            inner_html = node.html or ""

            # Remove a tag td externa para trabalhar só com o conteúdo
            inner = re.sub(r"^<td[^>]*>", "", inner_html, flags=re.IGNORECASE)
            inner = re.sub(r"</td>\s*$", "", inner, flags=re.IGNORECASE)

            # Divide por <br> (separa nome da parte dos blocos de advogado)
            blocos = re.split(r"<br\s*/?>", inner, flags=re.IGNORECASE)

            nome_parte = ""
            advogados_html: list[str] = []

            for i, bloco in enumerate(blocos):
                # Remove tags HTML restantes e decodifica entidades
                texto_bloco = re.sub(r"<[^>]+>", " ", bloco)
                texto_bloco = (
                    texto_bloco
                    .replace("&nbsp;", " ")
                    .replace("&amp;", "&")
                    .replace("&lt;", "<")
                    .replace("&gt;", ">")
                )
                texto_bloco = re.sub(r"[\s\xa0\u00a0]+", " ", texto_bloco).strip()

                if not texto_bloco:
                    continue

                if i == 0 and not re.match(r"^advogad[ao][:\s]", texto_bloco, re.IGNORECASE):
                    # Primeiro bloco antes de qualquer <br> = nome da parte
                    nome_parte = texto_bloco
                elif re.match(r"^advogad[ao][:\s]", texto_bloco, re.IGNORECASE):
                    advogados_html.append(texto_bloco)
                elif not nome_parte:
                    nome_parte = texto_bloco

            # Verifica também se há span.mensagemExibindo com rótulo de advogado,
            # extraindo o texto do nó após o span via regex no HTML original
            if not advogados_html:
                for m_adv in re.finditer(
                    r'<span[^>]*mensagemExibindo[^>]*>\s*(Advogad[ao][^<]*)</span>\s*([^<\n]+)',
                    inner, re.IGNORECASE
                ):
                    prefixo = re.sub(r"&nbsp;", " ", m_adv.group(1)).strip()
                    nome_adv_raw = re.sub(r"&nbsp;", " ", m_adv.group(2)).strip()
                    nome_adv_raw = re.sub(r"[\s\xa0]+", " ", nome_adv_raw).strip()
                    if nome_adv_raw:
                        advogados_html.append(f"{prefixo} {nome_adv_raw}")

            # Adiciona a parte principal
            if nome_parte and not re.match(r"^advogad[ao][:\s]", nome_parte, re.IGNORECASE):
                resultado.append(ParteProcesso(
                    nome=nome_parte.upper(),
                    tipo_parte=tipo_atual or "DESCONHECIDO",
                    polo=polo,
                ))

            # Adiciona advogados
            for texto_adv in advogados_html:
                nome_adv = re.sub(r"^advogad[ao][:\s]+", "", texto_adv, flags=re.IGNORECASE).strip()
                oab_m = re.search(r"OAB[/\s]*([A-Z]{2})\s*(\d{3,8})", nome_adv, re.IGNORECASE)
                oab_adv: Optional[str] = None
                if oab_m:
                    oab_adv = f"{oab_m.group(2)}{oab_m.group(1).upper()}"
                    nome_adv = re.sub(
                        r"\s*[-–]\s*OAB[/\s]*[A-Z]{2}\s*\d+", "",
                        nome_adv, flags=re.IGNORECASE,
                    ).strip()
                if nome_adv:
                    resultado.append(ParteProcesso(
                        nome=nome_adv.upper(),
                        tipo_parte="ADVOGADO",
                        polo=polo,
                        oab=oab_adv,
                    ))

        else:
            # --- Estrutura antiga: span.nomeParteEAdvogado ---
            raw = node.text()
            texto = re.sub(r"[\s\xa0\u00a0]+", " ", raw).strip()
            if not texto:
                return resultado

            if re.match(r"^advogad[ao][:\s]", texto, re.IGNORECASE):
                nome_adv = re.sub(r"^advogad[ao][:\s]+", "", texto, flags=re.IGNORECASE).strip()
                oab_m = re.search(r"OAB[/\s]*([A-Z]{2})\s*(\d{3,8})", nome_adv, re.IGNORECASE)
                oab_adv = None
                if oab_m:
                    oab_adv = f"{oab_m.group(2)}{oab_m.group(1).upper()}"
                    nome_adv = re.sub(
                        r"\s*[-–]\s*OAB[/\s]*[A-Z]{2}\s*\d+", "",
                        nome_adv, flags=re.IGNORECASE,
                    ).strip()
                if nome_adv:
                    resultado.append(ParteProcesso(
                        nome=nome_adv.upper(),
                        tipo_parte="ADVOGADO",
                        polo=polo,
                        oab=oab_adv,
                    ))
            else:
                resultado.append(ParteProcesso(
                    nome=texto.upper(),
                    tipo_parte=tipo_atual or "DESCONHECIDO",
                    polo=polo,
                ))

        return resultado

    def _polo_de_tipo(self, tipo: str) -> Optional[str]:
        # Formas completas e abreviadas usadas pelo TJSP (ex: "Reqte", "Reqda", "Impldo")
        ativos = {
            "REQUERENTE", "REQTE", "REQTES",
            "AUTOR", "AUTORA", "AUTORES",
            "IMPETRANTE", "IMPTE",
            "EXEQUENTE", "EXEQTE",
            "APELANTE", "APTE",
            "RECLAMANTE", "RECLTE",
            "EMBARGANTE", "EMBGTE",
            "AGRAVANTE", "AGTE",
        }
        passivos = {
            "REQUERIDO", "REQDO", "REQDA", "REQDOS", "REQDAS",
            "RÉU", "RÉ", "REU", "RE",
            "IMPETRADO", "IMPLDO", "IMPETRADA",
            "EXECUTADO", "EXECTDO",
            "APELADO", "APDO", "APELADA",
            "RECLAMADO", "RECLDDO",
            "EMBARGADO", "EMBGDO",
            "AGRAVADO", "AGDO",
            "INTERESDO", "INTERESSADO",
        }
        t = tipo.upper().rstrip(".")
        # Verifica substring — cobre "REQTE" dentro de "REQTES", etc.
        if any(a in t or t in a for a in ativos):
            return "ATIVO"
        if any(p in t or t in p for p in passivos):
            return "PASSIVO"
        return "OUTROS"

    def _extrair_partes_numero(self, numero_cnj: str) -> Optional[dict[str, str]]:
        m = re.match(r"(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})", numero_cnj)
        if not m:
            return None
        return {
            "processo": m.group(1), "digito": m.group(2),
            "ano": m.group(3), "justica": m.group(4),
            "tribunal": m.group(5), "origem": m.group(6),
        }

    @staticmethod
    def _foro_para_tjsp(foro: str) -> str:
        """
        Remove zeros à esquerda do código de foro para o formato que o TJSP espera.
        O número CNJ usa 4 dígitos com zero-padding (ex: '0050'), mas o eSaj
        espera o inteiro simples (ex: '50') no parâmetro processo.foro.
        """
        try:
            return str(int(foro))
        except (ValueError, TypeError):
            return foro
