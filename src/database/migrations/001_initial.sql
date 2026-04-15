-- ============================================================
-- JURIDICO CRAWLER - Schema inicial
-- Migração 001 - Criação de todas as tabelas
-- ============================================================

-- Extensões úteis
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- Busca por similaridade em nomes

-- ============================================================
-- PROCESSOS
-- ============================================================
CREATE TABLE IF NOT EXISTS processos (
    id SERIAL PRIMARY KEY,
    numero_cnj VARCHAR(30) UNIQUE NOT NULL,  -- ex: 0001234-56.2024.8.26.0001
    tribunal VARCHAR(20) NOT NULL,
    vara VARCHAR(200),
    comarca VARCHAR(200),
    classe_processual VARCHAR(200),
    assunto VARCHAR(500),
    valor_causa DECIMAL(15,2),
    data_distribuicao DATE,
    situacao VARCHAR(100),
    segredo_justica BOOLEAN DEFAULT FALSE,
    dados_brutos JSONB,
    criado_em TIMESTAMP DEFAULT NOW(),
    atualizado_em TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- PARTES
-- ============================================================
CREATE TABLE IF NOT EXISTS partes (
    id SERIAL PRIMARY KEY,
    processo_id INTEGER REFERENCES processos(id) ON DELETE CASCADE,
    tipo_parte VARCHAR(50) NOT NULL,  -- REQUERENTE, REQUERIDO, ADVOGADO, JUIZ, MP, etc.
    nome VARCHAR(300) NOT NULL,
    documento VARCHAR(20),            -- CPF ou CNPJ se disponível
    oab VARCHAR(20),                  -- Para advogados: ex. 123456SP
    polo VARCHAR(10),                 -- ATIVO, PASSIVO, OUTROS
    criado_em TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- MOVIMENTAÇÕES
-- ============================================================
CREATE TABLE IF NOT EXISTS movimentacoes (
    id SERIAL PRIMARY KEY,
    processo_id INTEGER REFERENCES processos(id) ON DELETE CASCADE,
    data_movimentacao DATE NOT NULL,
    tipo VARCHAR(200),
    descricao TEXT NOT NULL,
    complemento TEXT,
    codigo_nacional INTEGER,         -- Código tabela unificada CNJ
    criado_em TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- MONITORAMENTOS
-- ============================================================
CREATE TABLE IF NOT EXISTS monitoramentos (
    id SERIAL PRIMARY KEY,
    processo_id INTEGER REFERENCES processos(id) ON DELETE CASCADE,
    ativo BOOLEAN DEFAULT TRUE,
    ultima_verificacao TIMESTAMP,
    proxima_verificacao TIMESTAMP,
    notificar_email VARCHAR(200),
    criado_em TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- ÍNDICES DE PERFORMANCE
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_processos_numero ON processos(numero_cnj);
CREATE INDEX IF NOT EXISTS idx_processos_tribunal ON processos(tribunal);
CREATE INDEX IF NOT EXISTS idx_processos_situacao ON processos(situacao);
CREATE INDEX IF NOT EXISTS idx_processos_atualizado ON processos(atualizado_em DESC);

CREATE INDEX IF NOT EXISTS idx_partes_processo ON partes(processo_id);
CREATE INDEX IF NOT EXISTS idx_partes_nome ON partes(nome);
CREATE INDEX IF NOT EXISTS idx_partes_nome_trgm ON partes USING GIN (nome gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_partes_oab ON partes(oab) WHERE oab IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_partes_documento ON partes(documento) WHERE documento IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_partes_tipo ON partes(tipo_parte);

CREATE INDEX IF NOT EXISTS idx_movimentacoes_processo ON movimentacoes(processo_id);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_data ON movimentacoes(data_movimentacao DESC);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_codigo ON movimentacoes(codigo_nacional) WHERE codigo_nacional IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_monitoramentos_processo ON monitoramentos(processo_id);
CREATE INDEX IF NOT EXISTS idx_monitoramentos_proxima ON monitoramentos(proxima_verificacao) WHERE ativo = TRUE;

-- ============================================================
-- TRIGGER: atualizado_em automático
-- ============================================================
CREATE OR REPLACE FUNCTION update_atualizado_em()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_processos_atualizado_em
    BEFORE UPDATE ON processos
    FOR EACH ROW
    EXECUTE FUNCTION update_atualizado_em();
