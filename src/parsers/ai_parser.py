"""
Parser inteligente usando Claude (Anthropic) para extrair dados estruturados
de JSONs brutos do DataJud e outros tribunais.

Inclui também extrair_partes_do_datajud() — parser determinístico que trata
todas as variações de estrutura aninhada do DataJud sem depender de IA.
"""

import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import anthropic

from src.config import settings
from src.parsers.estruturas import MovimentacaoProcesso, ParteProcesso, ProcessoCompleto

logger = logging.getLogger(__name__)

_client: Optional[anthropic.AsyncAnthropic] = None


# ============================================================
# Parser determinístico de partes — sem depender de IA
# ============================================================

def normalizar_tipo_parte(tipo_raw: str) -> str:
    """Normaliza variações de tipo de parte para valores canônicos."""
    tipo_raw = tipo_raw.upper().strip()
    mapa = {
        "AUTOR": "REQUERENTE",
        "AUTORA": "REQUERENTE",
        "AUTORES": "REQUERENTE",
        "RECLAMANTE": "REQUERENTE",
        "IMPETRANTE": "REQUERENTE",
        "APELANTE": "REQUERENTE",
        "EXEQUENTE": "REQUERENTE",
        "EMBARGANTE": "REQUERENTE",
        "REU": "REQUERIDO",
        "RÉU": "REQUERIDO",
        "RÉ": "REQUERIDO",
        "REUS": "REQUERIDO",
        "RECLAMADO": "REQUERIDO",
        "IMPETRADO": "REQUERIDO",
        "APELADO": "REQUERIDO",
        "EXECUTADO": "REQUERIDO",
        "EMBARGADO": "REQUERIDO",
        "ADVOGADO": "ADVOGADO",
        "ADVOGADA": "ADVOGADO",
        "JUIZ": "JUIZ",
        "JUÍZA": "JUIZ",
        "DESEMBARGADOR": "JUIZ",
        "DESEMBARGADORA": "JUIZ",
        "MINISTÉRIO PÚBLICO": "MP",
        "MINISTERIO PUBLICO": "MP",
        "MP": "MP",
    }
    for chave, valor in mapa.items():
        if chave in tipo_raw:
            return valor
    return tipo_raw


def inferir_polo(tipo: str) -> str:
    """Infere o polo processual a partir do tipo normalizado."""
    ativos = {"REQUERENTE", "ADVOGADO_ATIVO"}
    passivos = {"REQUERIDO", "ADVOGADO_PASSIVO"}
    if tipo in ativos:
        return "ATIVO"
    if tipo in passivos:
        return "PASSIVO"
    return "OUTROS"


def limpar_documento(doc: Any) -> Optional[str]:
    """Remove formatação de CPF/CNPJ e valida tamanho mínimo."""
    if not doc:
        return None
    doc_str = str(doc).replace(".", "").replace("-", "").replace("/", "").strip()
    return doc_str if len(doc_str) >= 11 else None


def extrair_partes_do_datajud(source: dict) -> list[ParteProcesso]:
    """
    Extrai partes diretamente do JSON do DataJud sem depender de IA.
    Trata a estrutura aninhada: partes[].advogados[] e variações por tribunal.

    Args:
        source: dict _source retornado pelo ElasticSearch do DataJud

    Returns:
        Lista de ParteProcesso com todos os envolvidos encontrados
    """
    partes_extraidas: list[ParteProcesso] = []

    # ── Campo principal: "partes" ────────────────────────────────────
    for parte in source.get("partes", []):
        tipo_raw = (
            parte.get("tipoParte")
            or parte.get("tipo")
            or parte.get("polo")
            or "OUTRO"
        )
        tipo_norm = normalizar_tipo_parte(str(tipo_raw))
        polo = inferir_polo(tipo_norm)

        nome = (
            parte.get("nome")
            or parte.get("nomeRepresentado")
            or parte.get("nomeParte")
            or ""
        ).strip()

        if nome:
            partes_extraidas.append(ParteProcesso(
                nome=nome.upper(),
                tipo_parte=tipo_norm,
                polo=polo,
                documento=limpar_documento(
                    parte.get("cpf")
                    or parte.get("cnpj")
                    or parte.get("documento")
                    or parte.get("numeroDocumento")
                ),
                oab=None,
            ))

        # ── Advogados aninhados dentro de cada parte ─────────────────
        for adv in (parte.get("advogados") or parte.get("representantes") or []):
            nome_adv = (
                adv.get("nome") or adv.get("nomeAdvogado") or ""
            ).strip()
            if not nome_adv:
                continue

            oab_numero = str(
                adv.get("numeroOab")
                or adv.get("numeroOAB")
                or adv.get("oab")
                or adv.get("inscricaoOab")
                or ""
            ).strip()
            oab_uf = str(
                adv.get("ufOab")
                or adv.get("ufOAB")
                or adv.get("estadoOab")
                or ""
            ).strip()
            oab_fmt = f"{oab_numero}/{oab_uf}".strip("/") if oab_numero else None

            tipo_adv = "ADVOGADO"

            partes_extraidas.append(ParteProcesso(
                nome=nome_adv.upper(),
                tipo_parte=tipo_adv,
                polo=polo,
                documento=limpar_documento(
                    adv.get("cpf") or adv.get("documento")
                ),
                oab=oab_fmt,
            ))

    # ── Campo alternativo: magistrado/juiz ───────────────────────────
    orgao = source.get("orgaoJulgador", {})
    juiz = (
        source.get("magistrado")
        or source.get("juiz")
        or (orgao.get("magistrado") if isinstance(orgao, dict) else None)
    )
    if juiz and isinstance(juiz, str) and juiz.strip():
        partes_extraidas.append(ParteProcesso(
            nome=juiz.strip().upper(),
            tipo_parte="JUIZ",
            polo="OUTROS",
        ))

    # ── Estrutura legada TJSP: "parteAtiva" / "partePassiva" ─────────
    for campo, polo_leg, tipo_leg in [
        ("parteAtiva", "ATIVO", "REQUERENTE"),
        ("partePassiva", "PASSIVO", "REQUERIDO"),
    ]:
        val = source.get(campo)
        if not val:
            continue
        if isinstance(val, str) and val.strip():
            partes_extraidas.append(ParteProcesso(
                nome=val.strip().upper(),
                tipo_parte=tipo_leg,
                polo=polo_leg,
            ))
        elif isinstance(val, list):
            for item in val:
                nome = (item.get("nome", "") if isinstance(item, dict) else str(item)).strip()
                if nome:
                    partes_extraidas.append(ParteProcesso(
                        nome=nome.upper(),
                        tipo_parte=tipo_leg,
                        polo=polo_leg,
                    ))

    logger.debug(
        "extrair_partes_do_datajud: %d parte(s) extraída(s) de source com campos %s",
        len(partes_extraidas),
        list(source.keys()),
    )
    return partes_extraidas


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY não configurada. "
                "Defina no .env ou use usar_ai_parser=False."
            )
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


PROMPT_SISTEMA = """Você é um especialista em direito brasileiro e extração de dados jurídicos.
Analise o JSON bruto de um processo judicial e extraia as informações estruturadas com precisão.

Regras obrigatórias:
1. Retorne SOMENTE JSON válido, sem texto adicional, sem markdown, sem ```json
2. Normalize nomes em MAIÚSCULAS
3. Para OAB, use o formato: {número}{UF} ex: "123456SP"
4. Para CPF: apenas dígitos, 11 caracteres
5. Para CNPJ: apenas dígitos, 14 caracteres
6. Datas no formato ISO: YYYY-MM-DD
7. Valor da causa: número decimal, sem símbolos (ex: 15000.00)
8. Para tipo_parte use EXATAMENTE um destes valores:
   REQUERENTE, REQUERIDO, AUTOR, RÉU, ADVOGADO, JUIZ, PROMOTOR, PERITO,
   TERCEIRO_INTERESSADO, ASSISTENTE, CURADOR, INVENTARIANTE, DESCONHECIDO
9. Para polo use: ATIVO, PASSIVO ou OUTROS
10. Movimentações em ordem cronológica decrescente (mais recente primeiro)
11. Para cada movimentação, você deve definir:
    - categoria: uma destas: LIMINAR, CITACAO, AUDIENCIA, SENTENCA, RECURSO, DESPACHO_SIMPLES, OUTRO
    - impacto: uma destas: POSITIVO, NEGATIVO, NEUTRO, URGENTE
12. Se um campo não estiver disponível, use null"""

PROMPT_EXTRACAO = """Extraia os dados do seguinte JSON de processo judicial e retorne no formato abaixo.

JSON DO PROCESSO:
{dados_brutos}

FORMATO DE SAÍDA OBRIGATÓRIO (JSON puro):
{{
  "numero_cnj": "string",
  "tribunal": "string",
  "vara": "string ou null",
  "comarca": "string ou null",
  "classe_processual": "string ou null",
  "assunto": "string ou null",
  "valor_causa": "decimal string ou null",
  "data_distribuicao": "YYYY-MM-DD ou null",
  "situacao": "string ou null",
  "segredo_justica": false,
  "partes": [
    {{
      "nome": "NOME EM MAIÚSCULAS",
      "tipo_parte": "TIPO",
      "polo": "ATIVO|PASSIVO|OUTROS ou null",
      "documento": "apenas dígitos ou null",
      "oab": "123456SP ou null"
    }}
  ],
  "movimentacoes": [
    {{
      "data_movimentacao": "YYYY-MM-DD",
      "descricao": "string",
      "tipo": "string ou null",
      "codigo_nacional": "number ou null",
      "categoria": "LIMINAR | CITACAO | AUDIENCIA | SENTENCA | RECURSO | DESPACHO_SIMPLES | OUTRO",
      "impacto": "POSITIVO | NEGATIVO | NEUTRO | URGENTE"
    }}
  ]
}}"""


async def extrair_dados_completos(
    dados_brutos: dict[str, Any],
    tribunal: str = "",
) -> ProcessoCompleto:
    """
    Extrai dados estruturados de um processo usando Claude.

    Args:
        dados_brutos: JSON bruto retornado pelo DataJud ou outro tribunal
        tribunal: Sigla do tribunal para contexto adicional

    Returns:
        ProcessoCompleto com todos os campos extraídos
    """
    client = _get_client()

    # Limitar tamanho do JSON para não exceder o contexto do modelo
    dados_str = json.dumps(dados_brutos, ensure_ascii=False)
    if len(dados_str) > 50_000:
        logger.warning("JSON muito grande (%d chars), truncando para 50K", len(dados_str))
        dados_str = dados_str[:50_000] + "... [TRUNCADO]"

    prompt = PROMPT_EXTRACAO.format(dados_brutos=dados_str)
    if tribunal:
        prompt = f"Tribunal: {tribunal.upper()}\n\n" + prompt

    logger.debug("Enviando JSON para Claude parser (tribunal=%s)", tribunal)

    try:
        message = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=PROMPT_SISTEMA,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as e:
        logger.error("Erro na API Claude: %s", e)
        raise

    conteudo = message.content[0].text.strip()

    # Remover possível markdown caso o modelo adicione mesmo com a instrução
    if conteudo.startswith("```"):
        linhas = conteudo.split("\n")
        conteudo = "\n".join(linhas[1:-1] if linhas[-1] == "```" else linhas[1:])

    try:
        dados = json.loads(conteudo)
    except json.JSONDecodeError as e:
        logger.error("Claude retornou JSON inválido: %s\nConteúdo: %s", e, conteudo[:500])
        raise ValueError(f"AI parser retornou JSON inválido: {e}") from e

    return _montar_processo_completo(dados, dados_brutos, tribunal)


def _montar_processo_completo(
    dados: dict[str, Any],
    dados_brutos: dict[str, Any],
    tribunal: str,
) -> ProcessoCompleto:
    """Converte o dict extraído pelo Claude em um ProcessoCompleto tipado."""

    # Partes
    partes: list[ParteProcesso] = []
    for p in dados.get("partes", []):
        nome = p.get("nome", "").strip()
        if not nome:
            continue
        partes.append(ParteProcesso(
            nome=nome.upper(),
            tipo_parte=p.get("tipo_parte", "DESCONHECIDO").upper(),
            polo=p.get("polo"),
            documento=p.get("documento"),
            oab=p.get("oab"),
        ))

    # Movimentações
    movimentacoes: list[MovimentacaoProcesso] = []
    for m in dados.get("movimentacoes", []):
        data_str = m.get("data_movimentacao", "")
        descricao = m.get("descricao", "").strip()
        if not data_str or not descricao:
            continue
        try:
            data_mov = date.fromisoformat(data_str)
        except ValueError:
            logger.debug("Data inválida ignorada: %s", data_str)
            continue
        codigo = m.get("codigo_nacional")
        movimentacoes.append(MovimentacaoProcesso(
            data_movimentacao=data_mov,
            descricao=descricao,
            tipo=m.get("tipo"),
            complemento=m.get("complemento"),
            codigo_nacional=int(codigo) if codigo is not None else None,
        ))

    # Valor da causa
    valor_causa = None
    valor_raw = dados.get("valor_causa")
    if valor_raw is not None:
        try:
            valor_causa = Decimal(str(valor_raw))
        except InvalidOperation:
            logger.debug("Valor da causa inválido: %s", valor_raw)

    # Data de distribuição
    data_dist = None
    data_str = dados.get("data_distribuicao")
    if data_str:
        try:
            data_dist = date.fromisoformat(data_str)
        except ValueError:
            pass

    # Detecta segredo também nos dados brutos (mais confiável que o AI)
    nivel_sigilo_raw = dados_brutos.get("nivelSigilo", 0) or 0
    try:
        nivel_sigilo_int = int(nivel_sigilo_raw)
    except (TypeError, ValueError):
        nivel_sigilo_int = 0

    segredo = bool(dados.get("segredo_justica", False)) or nivel_sigilo_int > 0

    # Observações automáticas
    obs_lista: list[str] = []
    if segredo:
        obs_lista.append(
            f"Processo em SEGREDO DE JUSTIÇA (nível {nivel_sigilo_int}). "
            f"Dados podem estar omitidos pelo tribunal."
        )
    if not partes:
        obs_lista.append("Nenhuma parte extraída — considerar complementar via scraping.")
    if valor_causa is None:
        obs_lista.append("Valor da causa não informado — considerar complementar.")

    return ProcessoCompleto(
        numero_cnj=dados.get("numero_cnj", ""),
        tribunal=dados.get("tribunal", tribunal),
        vara=dados.get("vara"),
        comarca=dados.get("comarca"),
        classe_processual=dados.get("classe_processual"),
        assunto=dados.get("assunto"),
        valor_causa=valor_causa,
        data_distribuicao=data_dist,
        situacao="Segredo de Justiça" if segredo else dados.get("situacao"),
        segredo_justica=segredo,
        observacoes=" | ".join(obs_lista) if obs_lista else None,
        partes=partes,
        movimentacoes=sorted(movimentacoes, key=lambda x: x.data_movimentacao, reverse=True),
        dados_brutos=dados_brutos,
    )
