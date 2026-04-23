"""
Crawler TRF — Tribunais Regionais Federais.

Estratégias por tribunal:
  TRF1, TRF4   → eProc  (API REST pública + scraping)
  TRF2         → e-proc2 (variante) + PJe
  TRF3 (SP/MS) → eProc + portal próprio  ← mais relevante para OAB/SP
  TRF5         → PJe (coberto pelo PJeCrawler)

O eProc tem um endpoint de consulta pública que não exige CAPTCHA para
buscas por número CNJ, mas para busca por OAB usa o portal HTML.
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

# ──────────────────────────────────────────────────────────────────────
# Configuração dos portais TRF
# ──────────────────────────────────────────────────────────────────────

TRF_CONFIG: dict[str, dict] = {
    "trf1": {
        "nome": "TRF1 — 1ª Região (DF/MG/GO...)",
        "tipo": "eproc",
        "base": "https://eproc.trf1.jus.br/eproc2trf1",
        "busca_oab": "https://eproc.trf1.jus.br/eproc2trf1/controlador_externo.php",
        "busca_oab_params": {
            "acao": "advogado_processos",
            "acao_origem": "advogado_processos",
        },
    },
    "trf2": {
        "nome": "TRF2 — 2ª Região (RJ/ES)",
        "tipo": "eproc",
        "base": "https://eproc.trf2.jus.br/eproc",
        "busca_oab": "https://eproc.trf2.jus.br/eproc/controlador_externo.php",
        "busca_oab_params": {"acao": "advogado_processos"},
    },
    "trf3": {
        "nome": "TRF3 — 3ª Região (SP/MS)",
        "tipo": "eproc_e_pje",
        "base": "https://eproc.trf3.jus.br/eprocV2",
        "busca_oab": "https://eproc.trf3.jus.br/eprocV2/controlador_externo.php",
        "busca_oab_params": {"acao": "processo_selecionar"},
        # PJe do TRF3 (processos mais novos)
        "pje_base": "https://pje.trf3.jus.br/pje",
    },
    "trf4": {
        "nome": "TRF4 — 4ª Região (RS/SC/PR)",
        "tipo": "eproc",
        "base": "https://eproc.trf4.jus.br/eproc",
        "busca_oab": "https://eproc.trf4.jus.br/eproc/controlador_externo.php",
        "busca_oab_params": {"acao": "advogado_processos"},
    },
    "trf5": {
        "nome": "TRF5 — 5ª Região (NE)",
        "tipo": "pje",  # usa PJe — coberto pelo PJeCrawler
        "base": "https://pje.trf5.jus.br/consultaprocessual",
    },
}

TODOS_TRF = list(TRF_CONFIG.keys())


class TRFCrawler(BaseCrawler):
    """
    Crawler para os Tribunais Regionais Federais (TRF1 ao TRF5).

    Por padrão, foca no TRF3 (São Paulo / Mato Grosso do Sul)
    por ser o mais relevante para advogados com OAB/SP.

    Para busca por OAB, usa:
      1. API REST do TRF3 (quando disponível)
      2. eProc portal HTML + parse
      3. Firecrawl como fallback para portais com JS
    """

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }

    # ──────────────────────────────────────────────────────────────────
    # BUSCA POR OAB
    # ──────────────────────────────────────────────────────────────────

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str = "SP",
        tribunais: Optional[list[str]] = None,
        max_concorrentes: int = 3,
    ) -> list[ProcessoCompleto]:
        """
        Busca processos por OAB em um ou mais TRFs.
        Por padrão usa só TRF3 (SP/MS) para OABs com UF=SP.
        """
        alvos = tribunais or (["trf3"] if uf_oab.upper() == "SP" else TODOS_TRF)
        # Exclui TRF5 — coberto pelo PJeCrawler
        alvos = [t for t in alvos if TRF_CONFIG.get(t, {}).get("tipo") != "pje"]

        semaphore = asyncio.Semaphore(max_concorrentes)

        async def buscar_trf(tribunal: str) -> list[ProcessoCompleto]:
            async with semaphore:
                try:
                    return await self._buscar_trf(tribunal, numero_oab, uf_oab)
                except Exception as e:
                    logger.warning("TRF %s: erro OAB %s: %s", tribunal, numero_oab, e)
                    return []

        resultados: list[ProcessoCompleto] = []
        tasks = [buscar_trf(t) for t in alvos]
        for lista in await asyncio.gather(*tasks):
            resultados.extend(lista)

        logger.info("TRF: %d processo(s) para OAB %s/%s",
                    len(resultados), numero_oab, uf_oab)
        return resultados

    async def _buscar_trf(
        self,
        tribunal: str,
        numero_oab: str,
        uf_oab: str,
    ) -> list[ProcessoCompleto]:
        cfg = TRF_CONFIG.get(tribunal)
        if not cfg:
            return []

        tipo = cfg.get("tipo", "eproc")

        # TRF3 e outros com PJe: tenta API PJe primeiro (processos novos)
        pje_base = cfg.get("pje_base")
        if pje_base:
            processos = await self._buscar_pje_api(pje_base, numero_oab, uf_oab, tribunal)
            if processos:
                return processos

        # Portal eProc HTML — só tenta se NÃO for TRF3
        # (eProc do TRF3 exige autenticação para busca por OAB; timeout ~30s)
        if tipo == "eproc" and tribunal != "trf3":
            processos = await self._buscar_eproc_html(cfg, numero_oab, uf_oab, tribunal)
            if processos:
                return processos

        logger.info("%s: nenhum processo encontrado para OAB %s/%s",
                    tribunal.upper(), numero_oab, uf_oab)
        return []

    async def _buscar_pje_api(
        self,
        pje_base: str,
        numero_oab: str,
        uf_oab: str,
        tribunal: str,
    ) -> list[ProcessoCompleto]:
        """Busca via API PJe padrão (/api/v1/advogado/{oab}/processos)."""
        url = f"{pje_base}/api/v1/advogado/{numero_oab}/processos"
        params = {"uf": uf_oab.upper(), "pagina": 0, "tamanhoPagina": 100}
        try:
            resp = await self._get(url, params=params, timeout=15.0)
            if resp.status_code == 200:
                data = resp.json()
                processos = self._parse_json(data, tribunal)
                if processos:
                    logger.info("%s PJe: %d processo(s)", tribunal.upper(), len(processos))
                    return processos
                # API respondeu mas sem processos para esta OAB
                total = None
                if isinstance(data, dict):
                    total = data.get("totalElements", data.get("total", data.get("numberOfElements")))
                logger.info("%s PJe OAB %s/%s: sem processos (total=%s, chaves=%s)",
                            tribunal.upper(), numero_oab, uf_oab, total,
                            list(data.keys()) if isinstance(data, dict) else type(data).__name__)
                return []
            elif resp.status_code == 404:
                logger.debug("%s PJe: endpoint não existe (404)", tribunal.upper())
            else:
                logger.warning("%s PJe: status %d", tribunal.upper(), resp.status_code)
        except Exception as e:
            logger.debug("%s PJe API: %s", tribunal.upper(), e)
        return []

    async def _buscar_eproc_html(
        self,
        cfg: dict,
        numero_oab: str,
        uf_oab: str,
        tribunal: str,
    ) -> list[ProcessoCompleto]:
        """
        Busca via portal eProc HTML (sem Firecrawl — muito lento).

        O eProc público geralmente exige login para listar por OAB;
        a consulta pública só funciona por número de processo.
        Retorna lista vazia se não houver números CNJ no HTML.
        """
        url = cfg["busca_oab"]
        params = {
            **cfg.get("busca_oab_params", {}),
            "num_oab": numero_oab,
            "uf_oab": uf_oab.upper(),
        }
        try:
            resp = await self._get(url, params=params, timeout=10.0)
            if resp.status_code in (200, 302):
                processos = self._parse_html(resp.text, tribunal)
                if processos:
                    logger.info("%s eProc HTML: %d processo(s)", tribunal.upper(), len(processos))
                    return processos
        except Exception as e:
            logger.debug("%s eProc HTML: %s", tribunal.upper(), e)
        return []

    # ──────────────────────────────────────────────────────────────────
    # BUSCA POR CNJ
    # ──────────────────────────────────────────────────────────────────

    async def buscar_processo(
        self,
        numero_cnj: str,
        tribunal: str = "trf3",
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        """Busca processo específico no TRF pelo número CNJ."""
        cfg = TRF_CONFIG.get(tribunal.lower())
        if not cfg:
            return None

        # Tenta API REST TRF3
        api_rest = cfg.get("api_rest")
        if api_rest:
            try:
                resp = await self._get(f"{api_rest}/processo/{numero_cnj}")
                if resp.status_code == 200:
                    p = self._parse_detalhe_json(resp.json(), numero_cnj, tribunal)
                    if p:
                        return p
            except Exception as e:
                logger.debug("TRF3 API detalhe %s: %s", numero_cnj, e)

        # eProc consulta pública por número
        base = cfg["base"]
        url = f"{base}/controlador_externo.php"
        params = {
            "acao": "processo_selecionar",
            "num_processo": numero_cnj,
            "evento": "selecionar",
        }
        try:
            resp = await self._get(url, params=params)
            if resp.status_code == 200:
                processos = self._parse_html(resp.text, tribunal)
                if processos:
                    return processos[0]
        except Exception as e:
            logger.debug("TRF eProc consulta %s: %s", numero_cnj, e)

        return ProcessoCompleto(numero_cnj=numero_cnj, tribunal=tribunal)

    # ──────────────────────────────────────────────────────────────────
    # PARSERS
    # ──────────────────────────────────────────────────────────────────

    def _parse_json(self, data: Any, tribunal: str) -> list[ProcessoCompleto]:
        """Parse de resposta JSON genérica (lista ou dict com lista)."""
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

        result = []
        for item in itens:
            if not isinstance(item, dict):
                continue
            numero = (
                item.get("numeroProcesso")
                or item.get("numero")
                or item.get("nrProcesso")
                or ""
            )
            if not numero:
                continue
            numero = self._normalizar_cnj(numero)

            partes = self._extrair_partes_json(item)
            movs   = self._extrair_movs_json(item)
            valor  = self._parse_valor(
                item.get("valorCausa") or item.get("valor") or item.get("valorDaCausa")
            )
            data_d = self._parse_data(
                str(item.get("dataAjuizamento") or item.get("dataDistribuicao") or "")
            )
            result.append(ProcessoCompleto(
                numero_cnj=numero,
                tribunal=tribunal,
                vara=self._campo_str(item, "orgaoJulgador", "nomeOrgao") or item.get("vara"),
                classe_processual=self._campo_str(item, "classeProcessual", "descricao"),
                valor_causa=valor,
                data_distribuicao=data_d,
                partes=partes,
                movimentacoes=movs,
                dados_brutos=item,
            ))
        return result

    def _parse_detalhe_json(self, data: Any, numero_cnj: str, tribunal: str) -> Optional[ProcessoCompleto]:
        d = data.get("processo", data) if isinstance(data, dict) else {}
        processos = self._parse_json([d], tribunal)
        if processos:
            p = processos[0]
            p.numero_cnj = p.numero_cnj or numero_cnj
            return p
        return None

    def _parse_html(self, html: str, tribunal: str) -> list[ProcessoCompleto]:
        """
        Extrai números CNJ do HTML do portal eProc.

        O eProc lista processos em tabelas — procura padrão CNJ no texto.
        Se encontrar a tabela estruturada, extrai também vara e situação.
        """
        padrao_cnj = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
        numeros = list(dict.fromkeys(re.findall(padrao_cnj, html)))

        if not numeros:
            # Tenta padrão sem formatação (20 dígitos)
            raw = re.findall(r"\b(\d{20})\b", html)
            numeros = [self._normalizar_cnj(n) for n in raw]
            numeros = list(dict.fromkeys(n for n in numeros if n))

        if numeros:
            logger.info("%s HTML: %d número(s) CNJ encontrado(s)", tribunal.upper(), len(numeros))

        return [ProcessoCompleto(numero_cnj=n, tribunal=tribunal) for n in numeros]

    def _extrair_partes_json(self, item: dict) -> list[ParteProcesso]:
        partes: list[ParteProcesso] = []
        for polo_raw in item.get("polo", []):
            if not isinstance(polo_raw, dict):
                continue
            polo_letra = str(polo_raw.get("polo", "")).upper()
            polo_val = (
                "ATIVO" if polo_letra in ("A", "ATIVO") else
                "PASSIVO" if polo_letra in ("P", "PASSIVO") else "OUTROS"
            )
            for p in polo_raw.get("parte", []):
                if not isinstance(p, dict):
                    continue
                pessoa = p.get("pessoa", {})
                nome = (pessoa.get("nome") if isinstance(pessoa, dict) else None) or p.get("nome", "")
                if nome:
                    partes.append(ParteProcesso(nome=nome.upper(), tipo_parte="PARTE", polo=polo_val))
                for adv in p.get("advogado", []):
                    if not isinstance(adv, dict):
                        continue
                    nome_adv = adv.get("nome", "")
                    oab_num  = str(adv.get("numeroOAB", "") or "")
                    uf_adv   = str(adv.get("ufOAB", "") or "")
                    if nome_adv:
                        partes.append(ParteProcesso(
                            nome=nome_adv.upper(),
                            tipo_parte="ADVOGADO",
                            polo=polo_val,
                            oab=f"{oab_num}{uf_adv.upper()}" if oab_num else None,
                        ))
        return partes

    def _extrair_movs_json(self, item: dict) -> list[MovimentacaoProcesso]:
        movs: list[MovimentacaoProcesso] = []
        for m in item.get("movimento", item.get("movimentos", [])):
            if not isinstance(m, dict):
                continue
            data_str = (m.get("dataHora") or m.get("data") or "")[:10]
            desc = (
                (m.get("movimentoNacional", {}).get("descricao") if isinstance(m.get("movimentoNacional"), dict) else "")
                or m.get("complemento") or m.get("descricao") or ""
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
        s = re.sub(r"[^\d.\-]", "", str(numero)).strip()
        if re.match(r"^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$", s):
            return s
        digits = re.sub(r"\D", "", s)
        if len(digits) == 20:
            return f"{digits[:7]}-{digits[7:9]}.{digits[9:13]}.{digits[13]}.{digits[14:16]}.{digits[16:]}"
        return s

    @staticmethod
    def _campo_str(obj: dict, *keys: str) -> Optional[str]:
        for k in keys:
            obj = obj.get(k, {}) if isinstance(obj, dict) else {}
        return str(obj) if obj and not isinstance(obj, dict) else None

    @staticmethod
    def _parse_data(s: str) -> Optional[date]:
        if not s or len(s) < 8:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            for fmt in ("%d/%m/%Y",):
                try:
                    from datetime import datetime
                    return datetime.strptime(s[:10], fmt).date()
                except ValueError:
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
            if "," in s and "." in s:
                s = s.replace(".", "").replace(",", ".")
            elif "," in s:
                s = s.replace(",", ".")
            return Decimal(s) if s else None
        except (InvalidOperation, ValueError):
            return None
