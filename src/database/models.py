"""
Modelos SQLAlchemy que espelham o schema em 001_initial.sql.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    JSON,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Processo(Base):
    __tablename__ = "processos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_cnj: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    tribunal: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    grau: Mapped[Optional[str]] = mapped_column(String(30))  # G1, G2, RECURSAL, ORIGINARIO
    vara: Mapped[Optional[str]] = mapped_column(String(200))
    comarca: Mapped[Optional[str]] = mapped_column(String(200))
    classe_processual: Mapped[Optional[str]] = mapped_column(String(200))
    assunto: Mapped[Optional[str]] = mapped_column(String(500))
    valor_causa: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2))
    data_distribuicao: Mapped[Optional[date]] = mapped_column(Date)
    situacao: Mapped[Optional[str]] = mapped_column(String(100))
    segredo_justica: Mapped[bool] = mapped_column(Boolean, default=False)
    observacoes: Mapped[Optional[str]] = mapped_column(Text)  # anotações livres: segredo de justiça, completude de dados, etc.
    score_auditoria: Mapped[Optional[int]] = mapped_column(Integer)  # 0-100: confiabilidade da extração
    notas_auditoria: Mapped[Optional[dict]] = mapped_column(JSON)  # lista de notas/avisos do validador
    ultima_movimentacao_data: Mapped[Optional[date]] = mapped_column(Date, index=True)
    dados_brutos: Mapped[Optional[dict]] = mapped_column(JSON)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    partes: Mapped[list["Parte"]] = relationship(
        "Parte", back_populates="processo", cascade="all, delete-orphan"
    )
    movimentacoes: Mapped[list["Movimentacao"]] = relationship(
        "Movimentacao", back_populates="processo", cascade="all, delete-orphan"
    )
    monitoramentos: Mapped[list["Monitoramento"]] = relationship(
        "Monitoramento", back_populates="processo", cascade="all, delete-orphan"
    )
    prazos: Mapped[list["Prazo"]] = relationship(
        "Prazo", back_populates="processo", cascade="all, delete-orphan"
    )
    notificacoes: Mapped[list["Notificacao"]] = relationship(
        "Notificacao", back_populates="processo", cascade="all, delete-orphan"
    )


class Parte(Base):
    __tablename__ = "partes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processo_id: Mapped[int] = mapped_column(Integer, ForeignKey("processos.id", ondelete="CASCADE"))
    tipo_parte: Mapped[str] = mapped_column(String(50), nullable=False)
    nome: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    documento: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    oab: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    polo: Mapped[Optional[str]] = mapped_column(String(10))
    advogado_de_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("partes.id", ondelete="SET NULL"),
    )
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    processo: Mapped["Processo"] = relationship("Processo", back_populates="partes")
    advogado_de: Mapped[Optional["Parte"]] = relationship(
        "Parte", remote_side="Parte.id", foreign_keys=[advogado_de_id],
    )


class Movimentacao(Base):
    __tablename__ = "movimentacoes"
    __table_args__ = (
        Index("ix_movimentacoes_processo_data", "processo_id", "data_movimentacao"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processo_id: Mapped[int] = mapped_column(Integer, ForeignKey("processos.id", ondelete="CASCADE"))
    data_movimentacao: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    complemento: Mapped[Optional[str]] = mapped_column(Text)
    codigo_nacional: Mapped[Optional[int]] = mapped_column(Integer)
    categoria: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    impacto: Mapped[Optional[str]] = mapped_column(String(20))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    processo: Mapped["Processo"] = relationship("Processo", back_populates="movimentacoes")


class Monitoramento(Base):
    __tablename__ = "monitoramentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processo_id: Mapped[int] = mapped_column(Integer, ForeignKey("processos.id", ondelete="CASCADE"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    ultima_verificacao: Mapped[Optional[datetime]] = mapped_column(DateTime)
    proxima_verificacao: Mapped[Optional[datetime]] = mapped_column(DateTime)
    notificar_email: Mapped[Optional[str]] = mapped_column(String(200))
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    processo: Mapped["Processo"] = relationship("Processo", back_populates="monitoramentos")


class Notificacao(Base):
    """Registro de notificações enviadas sobre novas movimentações."""
    __tablename__ = "notificacoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processo_id: Mapped[int] = mapped_column(Integer, ForeignKey("processos.id", ondelete="CASCADE"))
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # NOVA_MOVIMENTACAO, PRAZO_VENCENDO
    resumo: Mapped[str] = mapped_column(Text, nullable=False)
    dados: Mapped[Optional[dict]] = mapped_column(JSON)
    lida: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    processo: Mapped["Processo"] = relationship("Processo", back_populates="notificacoes")


class Prazo(Base):
    """Prazos processuais calculados ou cadastrados manualmente."""
    __tablename__ = "prazos"
    __table_args__ = (
        Index("ix_prazos_vencimento", "data_vencimento", "cumprido"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    processo_id: Mapped[int] = mapped_column(Integer, ForeignKey("processos.id", ondelete="CASCADE"))
    tipo_prazo: Mapped[str] = mapped_column(String(100), nullable=False)  # CONTESTACAO, RECURSO, MANIFESTACAO, etc.
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_vencimento: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    dias_uteis: Mapped[Optional[int]] = mapped_column(Integer)
    cumprido: Mapped[bool] = mapped_column(Boolean, default=False)
    observacao: Mapped[Optional[str]] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    processo: Mapped["Processo"] = relationship("Processo", back_populates="prazos")


# ============================================================================
# MULTI-TENANT MODELS (Migration 005)
# ============================================================================

class TenantAccount(Base):
    """Contas de tenants (OABs)"""
    __tablename__ = "tenant_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_oab: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    uf: Mapped[str] = mapped_column(String(2), nullable=False)  # Ex: "SP", "RJ"
    nome_razao_social: Mapped[Optional[str]] = mapped_column(String(300))
    email_principal: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="ativo")  # ativo, suspenso, cancelado
    data_criacao: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    data_atualizacao: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    users: Mapped[list["TenantUser"]] = relationship(
        "TenantUser", back_populates="tenant", cascade="all, delete-orphan"
    )
    credenciais: Mapped[list["TenantCredencial"]] = relationship(
        "TenantCredencial", back_populates="tenant", cascade="all, delete-orphan"
    )


class TenantUser(Base):
    """Usuários por tenant"""
    __tablename__ = "tenant_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenant_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(200), nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # bcrypt hash
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="user")  # user, admin, viewer
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    data_criacao: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_login: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Índices
    __table_args__ = (
        Index("ix_tenant_users_email", "email"),
        Index("ix_tenant_users_role", "role"),
        Index("ix_tenant_users_tenant_email", "tenant_id", "email", unique=True),
    )

    # Relacionamentos
    tenant: Mapped["TenantAccount"] = relationship("TenantAccount", back_populates="users")


class TenantCredencial(Base):
    """Credenciais API (para integração com sistemas externos)"""
    __tablename__ = "tenant_credenciais"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenant_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    api_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    api_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    descricao: Mapped[Optional[str]] = mapped_column(String(200))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    data_criacao: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_uso: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Índices
    __table_args__ = (
        Index("ix_credenciais_api_key", "api_key"),
        Index("ix_credenciais_tenant_api_key", "tenant_id", "api_key", unique=True),
    )

    # Relacionamentos
    tenant: Mapped["TenantAccount"] = relationship("TenantAccount", back_populates="credenciais")


class AdvogadoCatalog(Base):
    """Catálogo global de advogados descobertos (Inteligência de Auto-Alimentação)"""
    __tablename__ = "advogado_catalog"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    numero_oab: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    uf: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    nome_completo: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    cpf: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    
    total_processos_encontrados: Mapped[int] = mapped_column(Integer, default=0)
    ultima_consulta_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Índice Composto para busca rápida de OAB/UF
    __table_args__ = (
        Index("ix_advogado_oab_uf", "numero_oab", "uf", unique=True),
    )
