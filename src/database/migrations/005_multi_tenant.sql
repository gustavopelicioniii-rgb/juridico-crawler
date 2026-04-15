-- Migration 005: Suporte Multi-Tenant
-- Adiciona isolamento de dados por OAB (tenant_id)

-- ============================================================================
-- TABELAS DE TENANT
-- ============================================================================

-- Contas de tenants (OABs)
CREATE TABLE IF NOT EXISTS tenant_accounts (
    id BIGSERIAL PRIMARY KEY,
    numero_oab VARCHAR(20) NOT NULL UNIQUE,  -- Ex: "361329SP"
    uf CHAR(2) NOT NULL,                     -- Ex: "SP"
    nome_razao_social VARCHAR(300),
    email_principal VARCHAR(200),
    status VARCHAR(20) DEFAULT 'ativo',      -- ativo, suspenso, cancelado
    data_criacao TIMESTAMP DEFAULT NOW(),
    data_atualizacao TIMESTAMP DEFAULT NOW(),

    CONSTRAINT unique_oab_uf UNIQUE(numero_oab, uf)
);

CREATE INDEX idx_tenant_numero_oab ON tenant_accounts(numero_oab);
CREATE INDEX idx_tenant_status ON tenant_accounts(status);

-- Usuários por tenant
CREATE TABLE IF NOT EXISTS tenant_users (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant_accounts(id) ON DELETE CASCADE,
    email VARCHAR(200) NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,       -- bcrypt hash
    nome VARCHAR(200) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',        -- user, admin, viewer
    ativo BOOLEAN DEFAULT TRUE,
    data_criacao TIMESTAMP DEFAULT NOW(),
    ultimo_login TIMESTAMP,

    CONSTRAINT unique_email_per_tenant UNIQUE(tenant_id, email)
);

CREATE INDEX idx_tenant_users_tenant ON tenant_users(tenant_id);
CREATE INDEX idx_tenant_users_email ON tenant_users(email);
CREATE INDEX idx_tenant_users_role ON tenant_users(role);

-- Credenciais API (para integração com sistemas externos)
CREATE TABLE IF NOT EXISTS tenant_credenciais (
    id BIGSERIAL PRIMARY KEY,
    tenant_id BIGINT NOT NULL REFERENCES tenant_accounts(id) ON DELETE CASCADE,
    api_key VARCHAR(100) NOT NULL UNIQUE,
    api_secret VARCHAR(255) NOT NULL,
    descricao VARCHAR(200),
    ativo BOOLEAN DEFAULT TRUE,
    data_criacao TIMESTAMP DEFAULT NOW(),
    ultimo_uso TIMESTAMP,

    UNIQUE(tenant_id, api_key)
);

CREATE INDEX idx_credenciais_tenant ON tenant_credenciais(tenant_id);
CREATE INDEX idx_credenciais_api_key ON tenant_credenciais(api_key);

-- ============================================================================
-- ADICIONAR tenant_id AOS MODELOS EXISTENTES
-- ============================================================================

-- 1. Processos
ALTER TABLE processos
ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT 1,
ADD CONSTRAINT fk_processos_tenant FOREIGN KEY (tenant_id) REFERENCES tenant_accounts(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_processos_tenant ON processos(tenant_id);
CREATE INDEX IF NOT EXISTS idx_processos_tenant_numero ON processos(tenant_id, numero_cnj);

-- 2. Partes
ALTER TABLE partes
ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT 1,
ADD CONSTRAINT fk_partes_tenant FOREIGN KEY (tenant_id) REFERENCES tenant_accounts(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_partes_tenant ON partes(tenant_id);

-- 3. Movimentações
ALTER TABLE movimentacoes
ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT 1,
ADD CONSTRAINT fk_movimentacoes_tenant FOREIGN KEY (tenant_id) REFERENCES tenant_accounts(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_movimentacoes_tenant ON movimentacoes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_tenant_data ON movimentacoes(tenant_id, data_movimentacao);

-- 4. Monitoramentos
ALTER TABLE monitoramentos
ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT 1,
ADD CONSTRAINT fk_monitoramentos_tenant FOREIGN KEY (tenant_id) REFERENCES tenant_accounts(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_monitoramentos_tenant ON monitoramentos(tenant_id);

-- 5. Notificações
ALTER TABLE notificacoes
ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT 1,
ADD CONSTRAINT fk_notificacoes_tenant FOREIGN KEY (tenant_id) REFERENCES tenant_accounts(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_notificacoes_tenant ON notificacoes(tenant_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_tenant_lida ON notificacoes(tenant_id, lida);

-- 6. Prazos
ALTER TABLE prazos
ADD COLUMN IF NOT EXISTS tenant_id BIGINT DEFAULT 1,
ADD CONSTRAINT fk_prazos_tenant FOREIGN KEY (tenant_id) REFERENCES tenant_accounts(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_prazos_tenant ON prazos(tenant_id);
CREATE INDEX IF NOT EXISTS idx_prazos_tenant_vencimento ON prazos(tenant_id, data_vencimento);

-- ============================================================================
-- ROW-LEVEL SECURITY (RLS) - Isolamento de Dados
-- ============================================================================

-- Habilitar RLS em todas as tabelas
ALTER TABLE processos ENABLE ROW LEVEL SECURITY;
ALTER TABLE partes ENABLE ROW LEVEL SECURITY;
ALTER TABLE movimentacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE monitoramentos ENABLE ROW LEVEL SECURITY;
ALTER TABLE notificacoes ENABLE ROW LEVEL SECURITY;
ALTER TABLE prazos ENABLE ROW LEVEL SECURITY;

-- Criar policies RLS (exemplo para processos)
-- O tenant_id vem do contexto da aplicação: app.current_tenant_id
CREATE POLICY processos_tenant_isolation ON processos
  USING (tenant_id = COALESCE(current_setting('app.current_tenant_id')::BIGINT, 0))
  WITH CHECK (tenant_id = COALESCE(current_setting('app.current_tenant_id')::BIGINT, 0));

CREATE POLICY partes_tenant_isolation ON partes
  USING (tenant_id = COALESCE(current_setting('app.current_tenant_id')::BIGINT, 0));

CREATE POLICY movimentacoes_tenant_isolation ON movimentacoes
  USING (tenant_id = COALESCE(current_setting('app.current_tenant_id')::BIGINT, 0));

CREATE POLICY monitoramentos_tenant_isolation ON monitoramentos
  USING (tenant_id = COALESCE(current_setting('app.current_tenant_id')::BIGINT, 0));

CREATE POLICY notificacoes_tenant_isolation ON notificacoes
  USING (tenant_id = COALESCE(current_setting('app.current_tenant_id')::BIGINT, 0));

CREATE POLICY prazos_tenant_isolation ON prazos
  USING (tenant_id = COALESCE(current_setting('app.current_tenant_id')::BIGINT, 0));

-- ============================================================================
-- SEED: Criar tenant inicial (OAB 361329)
-- ============================================================================

INSERT INTO tenant_accounts (numero_oab, uf, nome_razao_social, email_principal, status)
VALUES ('361329', 'SP', 'OAB São Paulo 361329', 'admin@oab361329.sp.br', 'ativo')
ON CONFLICT (numero_oab) DO NOTHING;

-- ============================================================================
-- ÍNDICES COMPOSTOS PARA PERFORMANCE
-- ============================================================================

-- Índices para queries comuns (tenant_id + outro campo)
CREATE INDEX IF NOT EXISTS idx_processos_tenant_situacao ON processos(tenant_id, situacao);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_tenant_tipo ON movimentacoes(tenant_id, tipo);
CREATE INDEX IF NOT EXISTS idx_monitoramentos_tenant_ativo ON monitoramentos(tenant_id, ativo);
CREATE INDEX IF NOT EXISTS idx_prazos_tenant_cumprido ON prazos(tenant_id, cumprido);

-- ============================================================================
-- COMENTÁRIOS
-- ============================================================================

COMMENT ON TABLE tenant_accounts IS 'Contas de OABs (tenants)';
COMMENT ON COLUMN tenant_accounts.numero_oab IS 'Número da OAB (ex: 361329SP)';
COMMENT ON TABLE tenant_users IS 'Usuários por tenant';
COMMENT ON TABLE tenant_credenciais IS 'Chaves de API por tenant para integração';
COMMENT ON COLUMN processos.tenant_id IS 'Isolamento de dados: qual tenant possui este processo';
