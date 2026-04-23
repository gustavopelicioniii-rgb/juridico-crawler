"""
Schemas para CRUD de Processos
"""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field
from typing import Optional


class ParteCreate(BaseModel):
    """Schema para criar uma parte."""
    tipo_parte: str = Field(..., min_length=1, max_length=50)
    nome: str = Field(..., min_length=1, max_length=300)
    documento: Optional[str] = Field(None, max_length=20)
    oab: Optional[str] = Field(None, max_length=20)
    polo: Optional[str] = Field(None, max_length=10)


class MovimentacaoCreate(BaseModel):
    """Schema para criar uma movimentação."""
    data_movimentacao: date
    descricao: str = Field(..., min_length=1)
    tipo: Optional[str] = Field(None, max_length=200)
    complemento: Optional[str] = None
    codigo_nacional: Optional[int] = None
    categoria: Optional[str] = Field(None, max_length=50)
    impacto: Optional[str] = Field(None, max_length=20)


class ProcessoCreate(BaseModel):
    """Schema para criar um processo."""
    numero_cnj: str = Field(..., min_length=1, max_length=30)
    tribunal: str = Field(..., min_length=1, max_length=20)
    grau: Optional[str] = Field(None, max_length=30)
    vara: Optional[str] = Field(None, max_length=200)
    comarca: Optional[str] = Field(None, max_length=200)
    classe_processual: Optional[str] = Field(None, max_length=200)
    assunto: Optional[str] = Field(None, max_length=500)
    valor_causa: Optional[Decimal] = None
    data_distribuicao: Optional[date] = None
    situacao: Optional[str] = Field(None, max_length=100)
    segredo_justica: bool = False
    observacoes: Optional[str] = None
    partes: list[ParteCreate] = []
    movimentacoes: list[MovimentacaoCreate] = []


class ProcessoUpdate(BaseModel):
    """Schema para atualizar um processo."""
    tribunal: Optional[str] = None
    grau: Optional[str] = None
    vara: Optional[str] = None
    comarca: Optional[str] = None
    classe_processual: Optional[str] = None
    assunto: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    data_distribuicao: Optional[date] = None
    situacao: Optional[str] = None
    segredo_justica: Optional[bool] = None
    observacoes: Optional[str] = None


class ParteResponse(BaseModel):
    """Response de uma parte."""
    id: int
    processo_id: int
    tipo_parte: str
    nome: str
    documento: Optional[str]
    oab: Optional[str]
    polo: Optional[str]

    class Config:
        from_attributes = True


class MovimentacaoResponse(BaseModel):
    """Response de uma movimentação."""
    id: int
    processo_id: int
    data_movimentacao: date
    tipo: Optional[str]
    descricao: str
    complemento: Optional[str]
    codigo_nacional: Optional[int]
    categoria: Optional[str]
    impacto: Optional[str]

    class Config:
        from_attributes = True


class ProcessoResponse(BaseModel):
    """Response completo de um processo."""
    id: int
    numero_cnj: str
    tribunal: str
    grau: Optional[str]
    vara: Optional[str]
    comarca: Optional[str]
    classe_processual: Optional[str]
    assunto: Optional[str]
    valor_causa: Optional[Decimal]
    data_distribuicao: Optional[date]
    situacao: Optional[str]
    segredo_justica: bool
    observacoes: Optional[str]
    score_auditoria: Optional[int]
    notas_auditoria: Optional[dict]
    ultima_movimentacao_data: Optional[date]
    criado_em: str
    atualizado_em: Optional[str]
    partes: list[ParteResponse] = []
    movimentacoes: list[MovimentacaoResponse] = []

    class Config:
        from_attributes = True


class ProcessoListResponse(BaseModel):
    """Response para listagem de processos (sem partes/movimentacoes)."""
    id: int
    numero_cnj: str
    tribunal: str
    situacao: Optional[str]
    score_auditoria: Optional[int]
    ultima_movimentacao_data: Optional[date]

    class Config:
        from_attributes = True


class MonitoramentoCreate(BaseModel):
    """Schema para criar monitoramento."""
    processo_id: int
    notificar_email: Optional[str] = Field(None, max_length=200)
    webhook_url: Optional[str] = Field(None, max_length=500)


class MonitoramentoResponse(BaseModel):
    """Response de monitoramento."""
    id: int
    processo_id: int
    ativo: bool
    ultima_verificacao: Optional[str]
    proxima_verificacao: Optional[str]
    notificar_email: Optional[str]
    webhook_url: Optional[str]
    criado_em: str

    class Config:
        from_attributes = True


class PrazoCreate(BaseModel):
    """Schema para criar prazo."""
    processo_id: int
    tipo_prazo: str = Field(..., min_length=1, max_length=100)
    descricao: str = Field(..., min_length=1)
    data_inicio: date
    data_vencimento: date
    dias_uteis: Optional[int] = None
    cumprido: bool = False
    observacao: Optional[str] = None


class PrazoUpdate(BaseModel):
    """Schema para atualizar prazo."""
    tipo_prazo: Optional[str] = None
    descricao: Optional[str] = None
    data_vencimento: Optional[date] = None
    dias_uteis: Optional[int] = None
    cumprido: Optional[bool] = None
    observacao: Optional[str] = None


class PrazoResponse(BaseModel):
    """Response de prazo."""
    id: int
    processo_id: int
    tipo_prazo: str
    descricao: str
    data_inicio: date
    data_vencimento: date
    dias_uteis: Optional[int]
    cumprido: bool
    observacao: Optional[str]
    criado_em: str

    class Config:
        from_attributes = True
