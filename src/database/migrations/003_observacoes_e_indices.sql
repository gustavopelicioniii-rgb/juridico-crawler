-- Migration 003: campo observacoes em processos + índices auxiliares
-- Data: 2026-04-07
-- Escopo: suporte a anotações livres (ex: flag de segredo de justiça) e busca por OAB

BEGIN;

-- 1. Campo observacoes em processos
ALTER TABLE processos
    ADD COLUMN IF NOT EXISTS observacoes TEXT;

COMMENT ON COLUMN processos.observacoes IS
    'Anotações livres: flag de segredo de justiça, completude de dados, notas manuais, etc.';

-- 2. Índice para buscas por segredo de justiça (facilita relatórios)
CREATE INDEX IF NOT EXISTS idx_processos_segredo
    ON processos(segredo_justica)
    WHERE segredo_justica = TRUE;

-- 3. Índice em partes.oab já existe (ver 001_initial.sql), mas garantimos busca case-insensitive
CREATE INDEX IF NOT EXISTS idx_partes_oab_lower
    ON partes(LOWER(oab))
    WHERE oab IS NOT NULL;

-- 4. Índice para processos sem valor da causa (facilita job de "complementar faltantes")
CREATE INDEX IF NOT EXISTS idx_processos_sem_valor
    ON processos(tribunal, atualizado_em DESC)
    WHERE valor_causa IS NULL;

COMMIT;
