"""
Dataclasses de saída padronizadas para dados de processos judiciais.
Usadas pelo AI Parser e pelos crawlers.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


def inferir_grau_cnj(numero_cnj: str) -> str:
    """
    Infere o grau do processo (G1, G2, RECURSAL, ORIGINARIO) a partir do número CNJ.

    Formato CNJ: NNNNNNN-DD.YYYY.N.NN.NNNN
    - Dígito 9 (0-indexed = posição 9) indica o grau:
      1 = G1 (Primeiro Grau)
      2 = G2 (Segundo Grau)
      3 = RECURSAL
      4+ = ORIGINARIO ou instâncias superiores
    """
    if not numero_cnj:
        return "G1"
    digits = re.sub(r"[^0-9]", "", numero_cnj)
    if len(digits) >= 10:
        grau_digit = digits[9]
        mapping = {
            "1": "G1",
            "2": "G2",
            "3": "RECURSAL",
            "4": "ORIGINARIO",
            "5": "ORIGINARIO",
            "6": "ORIGINARIO",
        }
        return mapping.get(grau_digit, "G1")
    return "G1"


@dataclass
class ParteProcesso:
    nome: str
    tipo_parte: str          # REQUERENTE, REQUERIDO, ADVOGADO, JUIZ, MP, PERITO, etc.
    polo: Optional[str] = None      # ATIVO, PASSIVO, OUTROS
    documento: Optional[str] = None  # CPF ou CNPJ
    oab: Optional[str] = None        # ex: 123456SP


@dataclass
class MovimentacaoProcesso:
    data_movimentacao: date
    descricao: str
    tipo: Optional[str] = None
    complemento: Optional[str] = None
    codigo_nacional: Optional[int] = None
    categoria: Optional[str] = None   # EX: LIMINAR, CITACAO, AUDIENCIA, SENTENCA, RECURSO
    impacto: Optional[str] = None     # EX: POSITIVO, NEGATIVO, NEUTRO, URGENTE


@dataclass
class ProcessoCompleto:
    numero_cnj: str
    tribunal: str
    grau: Optional[str] = None  # G1, G2, RECURSAL, ORIGINARIO
    vara: Optional[str] = None
    comarca: Optional[str] = None
    classe_processual: Optional[str] = None
    assunto: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    data_distribuicao: Optional[date] = None
    situacao: Optional[str] = None
    segredo_justica: bool = False
    observacoes: Optional[str] = None  # anotações livres (ex: "Processo em segredo de justiça — partes omitidas pelo tribunal")
    score_auditoria: Optional[int] = None # Confiabilidade 0-100 da extração
    notas_auditoria: list[str] = field(default_factory=list) # Notas/Avisos do robô validador
    partes: list[ParteProcesso] = field(default_factory=list)
    movimentacoes: list[MovimentacaoProcesso] = field(default_factory=list)
    dados_brutos: Optional[dict] = None
