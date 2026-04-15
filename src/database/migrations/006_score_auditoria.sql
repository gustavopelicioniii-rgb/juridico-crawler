-- Migration 006: Adiciona colunas de auditoria ao modelo Processo
-- Gerado em: 2026-04-11

ALTER TABLE processos
    ADD COLUMN IF NOT EXISTS score_auditoria INTEGER,
    ADD COLUMN IF NOT EXISTS notas_auditoria JSONB;

COMMENT ON COLUMN processos.score_auditoria IS 'Pontuação de confiabilidade da extração (0-100)';
COMMENT ON COLUMN processos.notas_auditoria IS 'Lista de notas/avisos do validador automático';
