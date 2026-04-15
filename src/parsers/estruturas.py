"""
Dataclasses de saída padronizadas para dados de processos judiciais.
Usadas pelo AI Parser e pelos crawlers.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional


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
