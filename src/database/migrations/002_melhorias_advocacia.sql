-- ============================================================
-- JURIDICO CRAWLER - Migration 002
-- Melhorias para uso em sistema de advocacia
-- - Novos campos em processos (grau, ultima_movimentacao_data)
-- - Novos campos em partes (advogado_de_id)
-- - Novos campos em movimentacoes (categoria, impacto)
-- - Novo campo em monitoramentos (webhook_url)
-- - Nova tabela: notificacoes
-- - Nova tabela: prazos
-- - Novos indices de performance
-- ============================================================

-- ============================================================
-- ALTERACOES EM TABELAS EXISTENTES
-- ============================================================

-- Processos: grau da instancia e ultima movimentacao
ALTER TABLE processos ADD COLUMN IF NOT EXISTS grau VARCHAR(30);
ALTER TABLE processos ADD COLUMN IF NOT EXISTS ultima_movimentacao_data DATE;

-- Partes: vinculo advogado -> parte que representa
ALTER TABLE partes ADD COLUMN IF NOT EXISTS advogado_de_id INTEGER REFERENCES partes(id) ON DELETE SET NULL;

-- Movimentacoes: classificacao e impacto
ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS categoria VARCHAR(50);
ALTER TABLE movimentacoes ADD COLUMN IF NOT EXISTS impacto VARCHAR(20);

-- Monitoramentos: webhook URL para notificacoes automaticas
ALTER TABLE monitoramentos ADD COLUMN IF NOT EXISTS webhook_url VARCHAR(500);

-- ============================================================
-- NOVA TABELA: NOTIFICACOES
-- ============================================================
CREATE TABLE IF NOT EXISTS notificacoes (
    id SERIAL PRIMARY KEY,
    processo_id INTEGER REFERENCES processos(id) ON DELETE CASCADE,
    tipo VARCHAR(50) NOT NULL,          -- NOVA_MOVIMENTACAO, PRAZO_VENCENDO
    resumo TEXT NOT NULL,
    dados JSONB,
    lida BOOLEAN DEFAULT FALSE,
    criado_em TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- NOVA TABELA: PRAZOS
-- ============================================================
CREATE TABLE IF NOT EXISTS prazos (
    id SERIAL PRIMARY KEY,
    processo_id INTEGER REFERENCES processos(id) ON DELETE CASCADE,
    tipo_prazo VARCHAR(100) NOT NULL,   -- CONTESTACAO, RECURSO, MANIFESTACAO, etc.
    descricao TEXT NOT NULL,
    data_inicio DATE NOT NULL,
    data_vencimento DATE NOT NULL,
    dias_uteis INTEGER,
    cumprido BOOLEAN DEFAULT FALSE,
    observacao TEXT,
    criado_em TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- NOVOS INDICES
-- ============================================================

-- Processos
CREATE INDEX IF NOT EXISTS idx_processos_ultima_mov ON processos(ultima_movimentacao_data DESC NULLS LAST);

-- Movimentacoes: indice composto para dedup e busca por categoria
CREATE INDEX IF NOT EXISTS idx_movimentacoes_processo_data ON movimentacoes(processo_id, data_movimentacao);
CREATE INDEX IF NOT EXISTS idx_movimentacoes_categoria ON movimentacoes(categoria) WHERE categoria IS NOT NULL;

-- Notificacoes
CREATE INDEX IF NOT EXISTS idx_notificacoes_processo ON notificacoes(processo_id);
CREATE INDEX IF NOT EXISTS idx_notificacoes_lida ON notificacoes(lida) WHERE lida = FALSE;
CREATE INDEX IF NOT EXISTS idx_notificacoes_criado ON notificacoes(criado_em DESC);

-- Prazos
CREATE INDEX IF NOT EXISTS idx_prazos_processo ON prazos(processo_id);
CREATE INDEX IF NOT EXISTS idx_prazos_vencimento ON prazos(data_vencimento, cumprido);
CREATE INDEX IF NOT EXISTS idx_prazos_pendentes ON prazos(data_vencimento ASC) WHERE cumprido = FALSE;
