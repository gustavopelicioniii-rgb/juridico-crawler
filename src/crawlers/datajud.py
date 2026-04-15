"""
Crawler para a API pública DataJud do CNJ.

Documentação: https://datajud-wiki.cnj.jus.br/api-publica/
Endpoint: POST https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search
Autenticação: Header APIKey (chave pública, sem cadastro)
"""

import asyncio
import json
import logging
from typing import Any, Optional

import httpx

from src.config import settings
from src.crawlers.base import BaseCrawler
from src.parsers.ai_parser import extrair_dados_completos
from src.parsers.estruturas import ProcessoCompleto

logger = logging.getLogger(__name__)

# ============================================================
# Mapeamento de tribunal → sufixo do endpoint DataJud
# Fonte: https://datajud-wiki.cnj.jus.br/api-publica/endpoints
# ============================================================
TRIBUNAL_ENDPOINT: dict[str, str] = {
    # Tribunais de Justiça Estaduais
    "tjac": "tjac",
    "tjal": "tjal",
    "tjam": "tjam",
    "tjap": "tjap",
    "tjba": "tjba",
    "tjce": "tjce",
    "tjdft": "tjdft",
    "tjes": "tjes",
    "tjgo": "tjgo",
    "tjma": "tjma",
    "tjmg": "tjmg",
    "tjms": "tjms",
    "tjmt": "tjmt",
    "tjpa": "tjpa",
    "tjpb": "tjpb",
    "tjpe": "tjpe",
    "tjpi": "tjpi",
    "tjpr": "tjpr",
    "tjrj": "tjrj",
    "tjrn": "tjrn",
    "tjro": "tjro",
    "tjrr": "tjrr",
    "tjrs": "tjrs",
    "tjsc": "tjsc",
    "tjse": "tjse",
    "tjsp": "tjsp",
    "tjto": "tjto",
    # Tribunais Regionais Federais
    "trf1": "trf1",
    "trf2": "trf2",
    "trf3": "trf3",
    "trf4": "trf4",
    "trf5": "trf5",
    "trf6": "trf6",
    # Tribunais Regionais do Trabalho
    "trt1": "trt1",
    "trt2": "trt2-sp",
    "trt3": "trt3",
    "trt4": "trt4",
    "trt5": "trt5",
    "trt6": "trt6",
    "trt7": "trt7",
    "trt8": "trt8",
    "trt9": "trt9",
    "trt10": "trt10",
    "trt11": "trt11",
    "trt12": "trt12",
    "trt13": "trt13",
    "trt14": "trt14",
    "trt15": "trt15",
    "trt16": "trt16",
    "trt17": "trt17",
    "trt18": "trt18",
    "trt19": "trt19",
    "trt20": "trt20",
    "trt21": "trt21",
    "trt22": "trt22",
    "trt23": "trt23",
    "trt24": "trt24",
    # Tribunais Superiores
    "stj": "stj",
    "stf": "stf",
    "tst": "tst",
    "tse": "tse",
    "stm": "stm",
    # Tribunais de Justiça Militar Estaduais
    "tjmmg": "tjmmg",
    "tjmrs": "tjmrs",
    "tjmsp": "tjmsp",
    # Tribunais Regionais Eleitorais
    "treac": "treac",
    "treal": "treal",
    "tream": "tream",
    "treap": "treap",
    "treba": "treba",
    "trece": "trece",
    "tredft": "tredft",
    "trees": "trees",
    "trego": "trego",
    "trema": "trema",
    "tremg": "tremg",
    "trems": "trems",
    "tremt": "tremt",
    "trepa": "trepa",
    "trepb": "trepb",
    "trepe": "trepe",
    "trepi": "trepi",
    "trepr": "trepr",
    "trerj": "trerj",
    "trern": "trern",
    "trero": "trero",
    "trerr": "trerr",
    "trers": "trers",
    "tresc": "tresc",
    "trese": "trese",
    "tresp": "tresp",
    "treto": "treto",
}


class DataJudCrawler(BaseCrawler):
    """
    Crawler oficial para o DataJud CNJ.
    Usa a API ElasticSearch pública sem necessidade de cadastro.
    """

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"APIKey {settings.datajud_api_key}",
            "Content-Type": "application/json",
        }

    def _get_endpoint(self, tribunal: str) -> str:
        """Retorna a URL completa do endpoint para o tribunal informado."""
        sufixo = TRIBUNAL_ENDPOINT.get(tribunal.lower())
        if not sufixo:
            raise ValueError(
                f"Tribunal '{tribunal}' não suportado. "
                f"Tribunais disponíveis: {list(TRIBUNAL_ENDPOINT.keys())}"
            )
        return f"{settings.datajud_base_url}/api_publica_{sufixo}/_search"

    def _montar_query(self, numero_cnj: str) -> dict[str, Any]:
        """Monta a query ElasticSearch para buscar por número CNJ."""
        return {
            "query": {
                "match": {
                    "numeroProcesso": numero_cnj
                }
            },
            "size": 1,
        }

    def _montar_query_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        tamanho: int = 100,
        search_after: Optional[list] = None,
    ) -> dict[str, Any]:
        """
        Monta query ElasticSearch para buscar todos os processos de um advogado pela OAB.
        O DataJud usa nested objects para partes.advogados.

        Gera MÚLTIPLAS variantes do número de OAB porque cada tribunal indexa de um jeito:
        - "361329"   (limpo)
        - "0361329"  (7 dígitos com pad)
        - "00361329" (8 dígitos com pad)
        """
        # Normaliza o número: remove zeros à esquerda e gera variantes com padding
        num_limpo = numero_oab.lstrip('0') or numero_oab
        variantes_oab: set[str] = {numero_oab, num_limpo}
        for tamanho_pad in (6, 7, 8):
            if len(num_limpo) <= tamanho_pad:
                variantes_oab.add(num_limpo.zfill(tamanho_pad))

        # Campos de sort que existem no DataJud (dataAjuizamento + _id para cursor estável)
        sort_fields: list[dict] = [
            {"dataAjuizamento": {"order": "desc", "unmapped_type": "date"}},
            {"_id": {"order": "asc"}},
        ]

        query: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": [
                        {
                            "bool": {
                                "should": [
                                    {"match": {"partes.advogados.numeroOAB": v}}
                                    for v in variantes_oab
                                ],
                                "minimum_should_match": 1,
                            }
                        },
                        {"match": {"partes.advogados.ufOAB": uf_oab.upper()}},
                    ]
                }
            },
            "size": tamanho,
            "_source": True,
            "sort": sort_fields,
        }
        if search_after is not None:
            query["search_after"] = search_after
        return query

    async def buscar_processo(
        self,
        numero_cnj: str,
        tribunal: str,  # type: ignore[override]
        usar_ai_parser: bool = True,
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        """
        Busca um processo no DataJud pelo número CNJ.

        Args:
            numero_cnj: Número no formato CNJ (ex: 0001234-56.2024.8.26.0001)
            tribunal: Sigla do tribunal (ex: 'tjsp', 'stj', 'trt2')
            usar_ai_parser: Se True, usa Claude para extrair dados estruturados

        Returns:
            ProcessoCompleto ou None se não encontrado
        """
        endpoint = self._get_endpoint(tribunal)
        query = self._montar_query(numero_cnj)

        try:
            response = await self._post(endpoint, json=query)
            data = response.json()
        except Exception as e:
            logger.error("Erro ao consultar DataJud para %s/%s: %s", tribunal, numero_cnj, e)
            raise

        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            logger.info("Processo não encontrado no DataJud: %s/%s", tribunal, numero_cnj)
            return None

        fonte = hits[0].get("_source", {})
        logger.info("Processo encontrado no DataJud: %s", numero_cnj)

        if usar_ai_parser:
            return await extrair_dados_completos(fonte, tribunal=tribunal)

        # Fallback: parsing básico sem AI
        return self._parse_basico(fonte, tribunal)

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        tribunais: Optional[list[str]] = None,
        tamanho_por_tribunal: int = 100,
        usar_ai_parser: bool = False,
        max_concorrentes: int = 50,
        paginar_ate_exaustao: bool = True,
        max_paginas_por_tribunal: int = 100,
    ) -> list[ProcessoCompleto]:
        """
        Busca todos os processos de um advogado pela OAB em um ou mais tribunais.
        As consultas aos tribunais rodam em paralelo (asyncio.gather + semáforo).

        Quando paginar_ate_exaustao=True, usa search_after para buscar TODAS as páginas
        de cada tribunal (limitado a max_paginas_por_tribunal por segurança).

        Args:
            numero_oab: Número da OAB sem UF (ex: "361329")
            uf_oab: UF da OAB (ex: "SP")
            tribunais: Lista de siglas de tribunais. Se None, busca em todos.
            tamanho_por_tribunal: Resultados por página (max 10000 no ES, prático 100-1000)
            usar_ai_parser: Se True, usa Claude para enriquecer cada processo
            max_concorrentes: Máximo de requisições paralelas ao DataJud
            paginar_ate_exaustao: Se True, pagina até não sobrar resultado
            max_paginas_por_tribunal: Teto de segurança contra loops infinitos

        Returns:
            Lista de ProcessoCompleto de todos os tribunais
        """
        alvos = tribunais or list(TRIBUNAL_ENDPOINT.keys())
        sem = asyncio.Semaphore(max_concorrentes)

        async def consultar_tribunal(tribunal: str) -> list[ProcessoCompleto]:
            async with sem:
                parciais: list[ProcessoCompleto] = []
                try:
                    endpoint = self._get_endpoint(tribunal)
                    search_after: Optional[list] = None

                    for pagina in range(max_paginas_por_tribunal):
                        query = self._montar_query_oab(
                            numero_oab, uf_oab, tamanho_por_tribunal, search_after=search_after,
                        )
                        response = await self._post(endpoint, json=query)
                        data = response.json()
                        hits = data.get("hits", {}).get("hits", [])
                        if not hits:
                            break

                        for hit in hits:
                            fonte = hit.get("_source", {})
                            if usar_ai_parser:
                                processo = await extrair_dados_completos(fonte, tribunal=tribunal)
                            else:
                                processo = self._parse_basico(fonte, tribunal)
                            parciais.append(processo)

                        # Se não estamos paginando ou chegamos ao fim, para
                        if not paginar_ate_exaustao or len(hits) < tamanho_por_tribunal:
                            break

                        # Próxima página: usa o sort do último hit como cursor
                        ultimo = hits[-1]
                        if "sort" not in ultimo:
                            break
                        search_after = ultimo["sort"]

                    if parciais:
                        logger.info(
                            "OAB %s/%s: %d processo(s) encontrado(s) no %s (%d página[s])",
                            numero_oab, uf_oab, len(parciais), tribunal.upper(), pagina + 1,
                        )
                    return parciais
                except httpx.HTTPStatusError as e:
                    if e.response.status_code in (401, 403):
                        logger.error("DataJud Erro de Autenticação (401/403): Chave de API inválida ou expirada.")
                        # Não adianta continuar tentando outros tribunais se a chave global falhou
                        raise ValueError("DATAJUD_AUTH_ERROR")
                    return parciais
                except ValueError as e:
                    if str(e) == "DATAJUD_AUTH_ERROR":
                        raise
                    return parciais
                except Exception as e:
                    logger.warning("Erro ao consultar %s para OAB %s: %s", tribunal, numero_oab, e)
                    return parciais

        grupos = await asyncio.gather(*[consultar_tribunal(t) for t in alvos])
        resultados: list[ProcessoCompleto] = [p for grupo in grupos for p in grupo]

        logger.info(
            "Busca OAB %s/%s concluída: %d processo(s) em %d tribunal(is)",
            numero_oab, uf_oab, len(resultados), len(alvos),
        )
        return resultados

    @staticmethod
    def _extrair_valor_causa(fonte: dict[str, Any]):
        """
        Extrai valor da causa tentando múltiplos campos e formatos.
        DataJud costuma trazer em 'valorCausa' (number), mas alguns tribunais mandam
        string com vírgula decimal ou dentro de campos alternativos aninhados.
        """
        from decimal import Decimal, InvalidOperation

        dados_basicos = fonte.get("dadosBasicos") if isinstance(fonte.get("dadosBasicos"), dict) else {}
        candidatos = [
            fonte.get("valorCausa"),
            fonte.get("valor_causa"),
            fonte.get("valorDaCausa"),
            dados_basicos.get("valorCausa"),
            dados_basicos.get("valor_causa"),
        ]
        for raw in candidatos:
            if raw is None or raw == "":
                continue
            try:
                if isinstance(raw, (int, float)):
                    val = Decimal(str(raw))
                    return val if val > 0 else None
                if isinstance(raw, str):
                    # Normaliza: "R$ 15.000,00" → "15000.00"
                    limpo = (
                        raw.replace("R$", "")
                        .replace(" ", "")
                        .replace(".", "")
                        .replace(",", ".")
                        .strip()
                    )
                    if limpo:
                        val = Decimal(limpo)
                        return val if val > 0 else None
            except (InvalidOperation, ValueError):
                continue
        return None

    @staticmethod
    def _detectar_segredo_justica(fonte: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Detecta se o processo está em segredo de justiça através de múltiplas heurísticas.
        Retorna (segredo: bool, observacao: Optional[str]).

        DataJud usa 'nivelSigilo' (0=público, 1..5=níveis de sigilo progressivo).
        Alguns tribunais marcam também em 'situacao' ou 'observacao'.
        """
        nivel = fonte.get("nivelSigilo")
        if nivel is None:
            nivel = (fonte.get("dadosBasicos") or {}).get("nivelSigilo", 0)
        try:
            nivel = int(nivel) if nivel is not None else 0
        except (TypeError, ValueError):
            nivel = 0

        situacao = str(fonte.get("situacao") or "").lower()
        segredo_por_texto = "segredo de justi" in situacao or "sigil" in situacao

        if nivel > 0 or segredo_por_texto:
            obs = (
                f"Processo em SEGREDO DE JUSTIÇA (nível {nivel}). "
                f"Dados de partes, valor da causa e movimentações podem estar omitidos ou parciais "
                f"pelo próprio tribunal — verificar junto ao órgão julgador."
            )
            return True, obs
        return False, None

    def _parse_basico(self, fonte: dict[str, Any], tribunal: str) -> ProcessoCompleto:
        """
        Parser básico sem AI — extrai campos diretos do JSON do DataJud.
        Usa extrair_partes_do_datajud() para tratar todas as variações de estrutura.
        """
        from src.parsers.estruturas import MovimentacaoProcesso
        from src.parsers.ai_parser import extrair_partes_do_datajud
        from datetime import date

        numero_cnj = fonte.get("numeroProcesso", "")

        # Logs de diagnóstico (DEBUG — só aparecem com LOG_LEVEL=DEBUG)
        logger.debug("DataJud _source campos: %s", list(fonte.keys()))
        logger.debug("DataJud partes raw count: %d", len(fonte.get("partes", [])))
        if fonte.get("partes"):
            logger.debug(
                "DataJud primeira parte: %s",
                json.dumps(fonte["partes"][0], ensure_ascii=False),
            )

        # Data de distribuição
        data_dist = None
        data_str = fonte.get("dataAjuizamento", "")
        if data_str:
            try:
                data_dist = date.fromisoformat(data_str[:10])
            except ValueError:
                pass

        # Partes — parser determinístico com fallbacks para todas as variações
        partes = extrair_partes_do_datajud(fonte)
        logger.info(
            "DataJud %s: %d parte(s) extraída(s)", numero_cnj or tribunal, len(partes)
        )

        # Movimentações
        movimentacoes = []
        for mov in fonte.get("movimentos", []):
            data_mov_str = mov.get("dataHora", "")[:10]
            try:
                data_mov = date.fromisoformat(data_mov_str)
            except ValueError:
                continue
            descricao = mov.get("nome", "") or mov.get("complemento", "Sem descrição")
            codigo = mov.get("codigo")
            movimentacoes.append(MovimentacaoProcesso(
                data_movimentacao=data_mov,
                descricao=descricao,
                codigo_nacional=int(codigo) if codigo else None,
            ))

        # Classe e assunto
        classe = fonte.get("classe", {})
        assuntos = fonte.get("assuntos", [])
        assunto_str = assuntos[0].get("nome") if assuntos else None

        # Valor da causa — extração robusta com múltiplos fallbacks
        valor_causa = self._extrair_valor_causa(fonte)

        # Segredo de justiça — nivelSigilo + situação
        segredo, obs_segredo = self._detectar_segredo_justica(fonte)

        # Observações: acumula segredo + flag de completude
        obs_partes: list[str] = []
        if obs_segredo:
            obs_partes.append(obs_segredo)
        if not partes:
            obs_partes.append("Nenhuma parte foi retornada pelo DataJud — considerar complementar via scraping do tribunal.")
        if valor_causa is None:
            obs_partes.append("Valor da causa não informado pelo DataJud — considerar complementar via scraping.")
        observacoes = " | ".join(obs_partes) if obs_partes else None

        orgao = fonte.get("orgaoJulgador", {}) or {}
        grau_raw = fonte.get("grau", "")

        return ProcessoCompleto(
            numero_cnj=numero_cnj,
            tribunal=tribunal,
            grau=grau_raw or None,
            vara=orgao.get("nome"),
            comarca=orgao.get("municipio") or orgao.get("nomeComarca") or str(orgao.get("codigoMunicipioIBGE", "") or ""),
            classe_processual=classe.get("nome") if isinstance(classe, dict) else str(classe),
            assunto=assunto_str,
            valor_causa=valor_causa,
            data_distribuicao=data_dist,
            situacao="Segredo de Justiça" if segredo else (grau_raw or "Ativo"),
            segredo_justica=segredo,
            observacoes=observacoes,
            partes=partes,
            movimentacoes=sorted(movimentacoes, key=lambda m: m.data_movimentacao, reverse=True),
            dados_brutos=fonte,
        )
