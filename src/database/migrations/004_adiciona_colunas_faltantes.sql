-- ============================================================
-- JURIDICO CRAWLER - Adiciona colunas faltantes
-- Migração 004 - Sincroniza schema com ORM models.py
-- ============================================================

-- Adiciona colunas faltantes na tabela processos
ALTER TABLE IF EXISTS processos
ADD COLUMN IF NOT EXISTS grau VARCHAR(30),
ADD COLUMN IF NOT EXISTS observacoes TEXT,
ADD COLUMN IF NOT EXISTS ultima_movimentacao_data DATE;

-- Adiciona colunas faltantes na tabela partes
ALTER TABLE IF EXISTS partes
ADD COLUMN IF NOT EXISTS advogado_de_id INTEGER REFERENCES partes(id) ON DELETE SET NULL;

-- Adiciona colunas faltantes na tabela movimentacoes
ALTER TABLE IF EXISTS movimentacoes
ADD COLUMN IF NOT EXISTS categoria VARCHAR(50),
ADD COLUMN IF NOT EXISTS impacto VARCHAR(20);

-- Adiciona colunas faltantes na tabela monitoramentos
ALTER TABLE IF EXISTS monitoramentos
ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(500);

-- Cria índices adicionais para performance
CREATE INDEX IF NOT EXISTS idx_processos_ultima_movimentacao ON processos(ultima_movimentacao_data DESC);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_processo_data ON movimentacoes(processo_id, data_movimentacao DESC);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_categoria ON movimentacoes(categoria) WHERE categoria IS NOT NULL;

-- Cria tabelas que podem estar faltando
CREATE TABLE IF NOT EXISTS notificacoes (
    id SERIAL PRIMARY KEY,
    processo_id INTEGER REFERENCES processos(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL,
    resumo TEXT NOT NULL,
    dados JSONB,
    lida BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS prazos (
    id SERIAL PRIMARY KEY,
    processo_id INTEGER REFERENCES processos(id) ON DELETE CASCADE,
    tipo_prazo VARCHAR(100) NOT NULL,
    descricao TEXT NOT NULL,
    data_inicio DATE NOT NULL,
    data_vencimento DATE NOT NULL,
    dias_uteis INTEGER,
    cumprido BOOLEAN DEFAULT FALSE,
    observacao TEXT,
    criado_em TIMESTAMP DEFAULT NOW()
);

-- Índices para notificacoes
CREATE INDEX IF NOT EXISTS idx_notificacoes_processo ON notificacoes(processo_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_tipo ON notificacoes(tipo);
CREATE INDEX IF NOT EXISTS idx_notificacoes_lida ON notificacoes(lida) WHERE lida = FALSE;

-- Índices para prazos
CREATE INDEX IF NOT EXISTS idx_prazos_processo ON prazos(processo_id);
CREATE INDEX IF NOT EXISTS idx_prazos_vencimento ON prazos(data_vencimento, cumprido);

-- ============================================================
-- Confirma sucesso
-- ============================================================
-- Execute this to verify:
-- SELECT column_name FROM information_schema.columns WHERE table_name='processos' ORDER BY column_name;
