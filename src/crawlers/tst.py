"""
Crawler TST — Tribunal Superior do Trabalho.

Usa a API REST pública de consulta processual do TST:
  https://consultaprocessual.tst.jus.br/consultaProcessual/rest/pje/advogado/{oab}

A API retorna JSON com paginação e inclui partes, movimentações e valor.
Não requer autenticação nem CAPTCHA para consultas públicas.
"""

from __future__ import annotations

import asyncio
import structlog
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import MovimentacaoProcesso, ParteProcesso, ProcessoCompleto

logger = structlog.get_logger(__name__)

# Endpoints do TST — dois sistemas coexistem:
#   PJe (processos novos):    pje.tst.jus.br/consultaprocessual
#   Portal legado (antigos):  consultaprocessual.tst.jus.br
TST_PJE_BASE    = "https://pje.tst.jus.br/consultaprocessual"
TST_LEGADO_BASE = "https://consultaprocessual.tst.jus.br"
TST_PORTAL      = TST_PJE_BASE


class TSTCrawler(BaseCrawler):
    """
    Crawler para o Tribunal Superior do Trabalho.

    Endpoints principais:
      GET /pje/advogado/{oab}?uf={uf}&pagina={n}&tamanhoPagina={size}
        → lista de processos do advogado

      GET /pje/processo/{numero_cnj}
        → detalhe de um processo específico
    """

    tribunal_id = "tst"

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, */*",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Referer": TST_PORTAL,
            "Origin": TST_PORTAL,
        }

    # ──────────────────────────────────────────────────────────────────
    # BUSCA POR OAB
    # ──────────────────────────────────────────────────────────────────

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str = "SP",
        paginas: int = 20,
        tamanho_pagina: int = 20,
    ) -> list[ProcessoCompleto]:
        """
        Busca todos os processos de um advogado no TST.

        Tenta em ordem:
          1. PJe TST → pje.tst.jus.br/consultaprocessual/api/v1/advogado/{oab}/processos
             - Se retornar 200 OK (mesmo com 0 resultados) → confiável, não tenta legado
             - Se retornar 404/erro → tenta portal legado
          2. Portal legado → consultaprocessual.tst.jus.br (HTML, só se PJe falhou)
        """
        # ── 1. PJe padrão ───────────────────────────────────────────────────
        resultados, pje_ok = await self._buscar_pje(numero_oab, uf_oab, paginas, tamanho_pagina)
        if resultados:
            return resultados

        # Se o PJe respondeu com 200 OK (pje_ok=True), não precisa tentar o legado
        # — o advogado simplesmente não tem processos no TST PJe.
        if pje_ok:
            logger.info("TST OAB %s/%s: 0 processo(s) no PJe (advogado sem processos TST)",
                        numero_oab, uf_oab)
            return []

        # ── 2. Portal legado HTML (só quando o PJe falhou completamente) ────
        logger.debug("TST OAB %s/%s: PJe falhou, tentando portal legado", numero_oab, uf_oab)
        resultados = await self._buscar_legado_html(numero_oab, uf_oab)
        if resultados:
            return resultados

        logger.info("TST OAB %s/%s: 0 processo(s) encontrado(s)", numero_oab, uf_oab)
        return []

    async def _buscar_pje(
        self,
        numero_oab: str,
        uf_oab: str,
        paginas: int,
        tamanho_pagina: int,
    ) -> tuple[list[ProcessoCompleto], bool]:
        """
        Busca via API PJe do TST.

        Retorna (resultados, pje_respondeu_200) onde:
          - pje_respondeu_200=True  → API existe e respondeu (mesmo que vazia)
          - pje_respondeu_200=False → API não encontrada (404) ou erro de rede
        """
        resultados: list[ProcessoCompleto] = []

        for pagina in range(0, paginas):
            url = f"{TST_PJE_BASE}/api/v1/advogado/{numero_oab}/processos"
            params: dict = {"uf": uf_oab.upper(), "pagina": pagina, "tamanhoPagina": tamanho_pagina}
            try:
                resp = await self._get(url, params=params)
                if resp.status_code == 404:
                    logger.debug("TST PJe: endpoint não encontrado (404)")
                    return [], False
                if resp.status_code not in (200, 202):
                    logger.warning("TST PJe OAB %s: status %d", numero_oab, resp.status_code)
                    return resultados, False

                # Verifica se o Content-Type é JSON — alguns tribunais retornam
                # 200 OK com HTML (página de login ou erro) em vez de JSON
                ct = resp.headers.get("content-type", "")
                if "json" not in ct:
                    logger.info("TST PJe OAB %s: resposta não é JSON (Content-Type=%s) — "
                                "endpoint existe mas sem API REST JSON", numero_oab, ct)
                    # Endpoint existe mas não serve JSON → marca como "respondeu"
                    # para não tentar o portal legado (que provavelmente também vai falhar)
                    return resultados, True

                try:
                    data = resp.json()
                except Exception as json_err:
                    logger.info("TST PJe OAB %s: 200 OK mas resposta não é JSON válido: %s",
                                numero_oab, json_err)
                    return resultados, True  # "respondeu" mas sem dados — não tenta legado

                processos_pagina = self._parse_lista(data)

                if not processos_pagina:
                    if isinstance(data, dict):
                        total = data.get("totalElements", data.get("total", 0))
                        logger.info("TST PJe OAB %s: página %d sem itens (total=%s, chaves=%s)",
                                    numero_oab, pagina, total, list(data.keys()))
                    # API respondeu 200 OK com lista vazia — confirma que não há processos
                    return resultados, True

                resultados.extend(processos_pagina)
                logger.info("TST PJe OAB %s/%s: página %d → +%d (total %d)",
                            numero_oab, uf_oab, pagina, len(processos_pagina), len(resultados))

                if len(processos_pagina) < tamanho_pagina:
                    return resultados, True

            except Exception as e:
                logger.debug("TST PJe OAB %s: erro página %d: %s", numero_oab, pagina, e)
                return resultados, False

        return resultados, True

    async def _buscar_legado_html(self, numero_oab: str, uf_oab: str) -> list[ProcessoCompleto]:
        """
        Busca no portal legado do TST (processos mais antigos, pré-PJe).
        URL: https://consultaprocessual.tst.jus.br/consultaProcessual/Processo.do
        """
        import re
        url = f"{TST_LEGADO_BASE}/consultaProcessual/Processo.do"
        params = {
            "query": numero_oab,
            "uf": uf_oab.upper(),
            "tipoConsulta": "advogado",
            "ConsultaRapida": "Consultar",
        }
        try:
            resp = await self._get(url, params=params)
            if resp.status_code == 200:
                html = resp.text
                # Extrai números CNJ do HTML
                numeros = list(dict.fromkeys(
                    re.findall(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", html)
                ))
                if numeros:
                    logger.info("TST legado OAB %s: %d número(s) encontrado(s)", numero_oab, len(numeros))
                    return [ProcessoCompleto(numero_cnj=n, tribunal="tst") for n in numeros]
        except Exception as e:
            logger.debug("TST legado OAB %s: %s", numero_oab, e)

        # Fallback Firecrawl
        try:
            from src.crawlers.firecrawl_client import get_firecrawl_client
            from urllib.parse import urlencode
            fc = get_firecrawl_client()
            if fc:
                full_url = f"{url}?{urlencode(params)}"
                html_fc = await fc.scrape_html(full_url)
                if html_fc:
                    numeros = list(dict.fromkeys(
                        re.findall(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", html_fc)
                    ))
                    if numeros:
                        logger.info("TST Firecrawl OAB %s: %d número(s)", numero_oab, len(numeros))
                        return [ProcessoCompleto(numero_cnj=n, tribunal="tst") for n in numeros]
        except Exception as e:
            logger.debug("TST Firecrawl OAB %s: %s", numero_oab, e)

        return []

    # ──────────────────────────────────────────────────────────────────
    # BUSCA POR CNJ
    # ──────────────────────────────────────────────────────────────────

    async def buscar_processo(
        self,
        numero_cnj: str,
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        """Busca um processo específico no TST pelo número CNJ."""
        url = f"{TST_API_BASE}/processo/{numero_cnj}"
        try:
            resp = await self._get(url)
            if resp.status_code == 200:
                return self._parse_detalhe(resp.json(), numero_cnj)
        except Exception as e:
            logger.debug("TST: erro ao buscar %s: %s", numero_cnj, e)
        return None

    # ──────────────────────────────────────────────────────────────────
    # PARSERS
    # ──────────────────────────────────────────────────────────────────

    def _parse_lista(self, data: Any) -> list[ProcessoCompleto]:
        """
        Parse da resposta da API de lista por advogado.

        A API TST pode retornar:
          - lista direta: [{...}, ...]
          - dict com chave 'processos', 'content', 'data', 'records', 'lista'
          - dict com 'itens' ou 'result'
        """
        itens: list[dict] = []

        if isinstance(data, list):
            itens = data
        elif isinstance(data, dict):
            for chave in ("processos", "content", "data", "records", "lista",
                          "itens", "result", "results"):
                v = data.get(chave)
                if isinstance(v, list) and v:
                    itens = v
                    break

        processos = []
        for item in itens:
            if not isinstance(item, dict):
                continue
            p = self._montar_processo(item)
            if p and p.numero_cnj:
                processos.append(p)
        return processos

    def _parse_detalhe(self, data: Any, numero_cnj: str) -> Optional[ProcessoCompleto]:
        """Parse da resposta do endpoint de detalhe."""
        if isinstance(data, dict):
            # Pode vir embrulhado em chave 'processo'
            d = data.get("processo") if "processo" in data else data
            p = self._montar_processo(d)
            if p:
                p.numero_cnj = p.numero_cnj or numero_cnj
                return p
        return None

    def _montar_processo(self, item: dict) -> Optional[ProcessoCompleto]:
        """Constrói ProcessoCompleto a partir de um item da API TST."""
        # Número do processo — variações de nomes de campo observadas na API
        numero = (
            item.get("numeroProcesso")
            or item.get("numero")
            or item.get("numeroDoProcesso")
            or item.get("num_processo")
            or item.get("nrProcesso")
            or ""
        )
        if not numero:
            return None

        # Normaliza o número para o formato CNJ se necessário
        numero = self._normalizar_cnj(numero)

        # Vara / órgão julgador
        vara = self._campo_str(item, "orgaoJulgador", "nomeOrgao") \
            or self._campo_str(item, "orgao", "nome") \
            or item.get("vara") \
            or item.get("nomeOrgaoJulgador")

        # Classe processual
        classe = self._campo_str(item, "classeProcessual", "descricao") \
            or item.get("classe") \
            or item.get("classeProcessual") \
            or item.get("descricaoClasse")

        # Assunto
        assunto = self._campo_str(item, "assunto", "descricao") \
            or item.get("assunto")

        # Valor da causa
        valor_causa: Optional[Decimal] = None
        for campo_valor in ("valorCausa", "valor", "valorDaCausa", "valorAcao"):
            v = item.get(campo_valor)
            if v is not None:
                valor_causa = self._parse_valor(v)
                if valor_causa:
                    break

        # Data de ajuizamento / distribuição
        data_dist: Optional[date] = None
        for campo_data in ("dataAjuizamento", "dataDistribuicao", "dtAjuizamento",
                           "dataAbertura", "dtDistribuicao"):
            ds = item.get(campo_data, "")
            if ds:
                data_dist = self._parse_data(str(ds))
                if data_dist:
                    break

        # Situação / status
        situacao = (
            item.get("situacao")
            or item.get("status")
            or self._campo_str(item, "situacaoProcesso", "descricao")
        )

        # Segredo de justiça
        nivel_sigilo = item.get("nivelSigilo") or item.get("grauSigilo") or 0
        try:
            nivel_sigilo = int(nivel_sigilo)
        except (TypeError, ValueError):
            nivel_sigilo = 0
        segredo = nivel_sigilo > 0
        obs = f"Processo em segredo de justiça (nível {nivel_sigilo})" if segredo else None

        # Partes
        partes = self._extrair_partes(item)

        # Movimentações
        movs = self._extrair_movs(item)

        return ProcessoCompleto(
            numero_cnj=numero,
            tribunal="tst",
            vara=str(vara) if vara else None,
            comarca=None,
            classe_processual=str(classe) if classe else None,
            assunto=str(assunto) if assunto else None,
            valor_causa=valor_causa,
            data_distribuicao=data_dist,
            situacao=str(situacao) if situacao else None,
            segredo_justica=segredo,
            observacoes=obs,
            partes=partes,
            movimentacoes=movs,
            dados_brutos=item,
        )

    def _extrair_partes(self, item: dict) -> list[ParteProcesso]:
        """
        Extrai partes e advogados de um processo TST.

        A API TST usa estrutura similar ao PJe:
          "polo": [{"polo": "A", "parte": [{"pessoa": {"nome": "..."}, "advogado": [...]}]}]

        Mas também pode usar:
          "partes": [{"nome": "...", "polo": "ATIVO", "advogados": [...]}]
        """
        partes: list[ParteProcesso] = []

        # Estrutura PJe-padrão: polo > parte > pessoa + advogado
        for polo_raw in item.get("polo", []):
            if not isinstance(polo_raw, dict):
                continue
            polo_letra = str(polo_raw.get("polo", "")).upper()
            polo_val = (
                "ATIVO" if polo_letra in ("A", "ATIVO", "AUTOR", "RECLAMANTE") else
                "PASSIVO" if polo_letra in ("P", "PASSIVO", "REU", "RECLAMADO") else
                "OUTROS"
            )
            for p in polo_raw.get("parte", []):
                if not isinstance(p, dict):
                    continue
                pessoa = p.get("pessoa", {})
                nome = (
                    (pessoa.get("nome") if isinstance(pessoa, dict) else None)
                    or p.get("nome")
                    or ""
                )
                if not nome:
                    continue
                tipo = "PARTE"
                if isinstance(p.get("tipoParte"), dict):
                    tipo = p["tipoParte"].get("descricao", "PARTE").upper()
                partes.append(ParteProcesso(nome=nome.upper(), tipo_parte=tipo, polo=polo_val))

                for adv in p.get("advogado", []):
                    if not isinstance(adv, dict):
                        continue
                    nome_adv = adv.get("nome", "")
                    oab_num  = str(adv.get("numeroOAB", "") or adv.get("numOAB", ""))
                    uf_adv   = str(adv.get("ufOAB", "") or adv.get("uf", ""))
                    if nome_adv:
                        partes.append(ParteProcesso(
                            nome=nome_adv.upper(),
                            tipo_parte="ADVOGADO",
                            polo=polo_val,
                            oab=f"{oab_num}{uf_adv.upper()}" if oab_num else None,
                        ))

        # Estrutura alternativa: "partes" como lista plana
        if not partes:
            for p in item.get("partes", []):
                if not isinstance(p, dict):
                    continue
                nome = p.get("nome", "")
                if not nome:
                    continue
                polo_raw2 = str(p.get("polo", "")).upper()
                polo_val2 = (
                    "ATIVO" if "ATIVO" in polo_raw2 or "AUTOR" in polo_raw2 or polo_raw2 == "A" else
                    "PASSIVO" if "PASSIVO" in polo_raw2 or "REU" in polo_raw2 or polo_raw2 == "P" else
                    "OUTROS"
                )
                tipo2 = str(p.get("tipo", p.get("tipoParte", "PARTE"))).upper()
                partes.append(ParteProcesso(nome=nome.upper(), tipo_parte=tipo2, polo=polo_val2))

                for adv in p.get("advogados", p.get("advogado", [])):
                    if not isinstance(adv, dict):
                        continue
                    nome_adv = adv.get("nome", "")
                    oab_num  = str(adv.get("numeroOAB", "") or adv.get("numOAB", ""))
                    uf_adv   = str(adv.get("ufOAB", "") or adv.get("uf", ""))
                    if nome_adv:
                        partes.append(ParteProcesso(
                            nome=nome_adv.upper(),
                            tipo_parte="ADVOGADO",
                            polo=polo_val2,
                            oab=f"{oab_num}{uf_adv.upper()}" if oab_num else None,
                        ))

        return partes

    def _extrair_movs(self, item: dict) -> list[MovimentacaoProcesso]:
        """Extrai movimentações do processo TST."""
        movs: list[MovimentacaoProcesso] = []
        for m in item.get("movimento", item.get("movimentos", item.get("movimentacoes", []))):
            if not isinstance(m, dict):
                continue
            data_str = (
                m.get("dataHora", "")
                or m.get("data", "")
                or m.get("dtMovimento", "")
            )[:10]
            desc = (
                (m.get("movimentoNacional", {}).get("descricao") if isinstance(m.get("movimentoNacional"), dict) else "")
                or m.get("complemento")
                or m.get("descricao")
                or m.get("titulo")
                or ""
            )
            d = self._parse_data(data_str)
            if d and desc:
                movs.append(MovimentacaoProcesso(data_movimentacao=d, descricao=str(desc)[:500]))
        return sorted(movs, key=lambda x: x.data_movimentacao, reverse=True)

    # ──────────────────────────────────────────────────────────────────
    # Utilitários
    # ──────────────────────────────────────────────────────────────────

    @staticmethod
    def _normalizar_cnj(numero: str) -> str:
        """Garante que o número está no formato CNJ (NNNNNNN-DD.AAAA.J.TT.OOOO)."""
        # Remove qualquer coisa que não seja dígito ou separadores CNJ
        s = re.sub(r"[^\d.\-]", "", str(numero)).strip()
        # Já está no formato correto?
        if re.match(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$", s):
            return s
        # Tenta extrair apenas os dígitos e reformatar
        digits = re.sub(r"\D", "", s)
        if len(digits) == 20:
            return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"
        return s  # devolve o original se não conseguiu normalizar

    @staticmethod
    def _campo_str(obj: dict, *keys: str) -> Optional[str]:
        for k in keys:
            obj = obj.get(k, {}) if isinstance(obj, dict) else {}
        return str(obj) if obj and not isinstance(obj, dict) else None

    @staticmethod
    def _parse_data(s: str) -> Optional[date]:
        if not s:
            return None
        # Aceita formatos: YYYY-MM-DD, DD/MM/YYYY, YYYY-MM-DDTHH:MM:SS
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return date(*[int(x) for x in re.split(r"[-/T]", s[:10])])
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def _parse_valor(v: Any) -> Optional[Decimal]:
        if v is None:
            return None
        try:
            if isinstance(v, (int, float)):
                return Decimal(str(v))
            s = re.sub(r"[^\d,.]", "", str(v))
            # Formato brasileiro: 1.234,56 → 1234.56
            if "," in s and "." in s:
                s = s.replace(".", "").replace(",", ".")
            elif "," in s:
                s = s.replace(",", ".")
            return Decimal(s) if s else None
        except (InvalidOperation, ValueError):
            return None
