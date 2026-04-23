# Auditoria Funcional Completa — juridico-crawler

**Data:** 2026-04-23
**Repositório:** github.com/gustavopelicioniii-rgb/juridico-crawler
**Commit:** a2a02ac (após correções críticas)

---

## 1. Resumo Executivo

| Aspecto | Status | Nota |
|---------|--------|------|
| **Funcionalidade de Busca** | ✅ Funcional | 9/10 |
| **CRUD de Processos** | ✅ Implementado | 8/10 |
| **Persistência de Dados** | ✅ Funcional | 8/10 |
| **Multi-Tenant Auth** | ✅ Funcional | 7/10 |
| **CRUD Monitoramentos** | ✅ Implementado | 8/10 |
| **CRUD Prazos** | ✅ Implementado | 8/10 |
| **Gestão Notificações** | ✅ Implementado | 8/10 |
| **Catálogo Advogados** | ✅ Implementado | 7/10 |
| **Dashboard** | Básico (HTML hardcoded) | 3/10 |
| **Cobertura de Tribunais** | Boa (14+ crawlers) | 8/10 |
| **Extração de Dados** | Boa (partes, movs, valores) | 8/10 |
| **Testes** | Mínimos | 3/10 |

**NOTA GERAL FUNCIONALIDADE:** **7.5/10** *(antes: 5.5/10)*

---

## 2. ✅ Problemas CRÍTICOS RESOLVIDOS

### ✅ 2.1 CRUD de Processos — RESOLVIDO
- `POST /api/processos` — criar processo
- `PUT /api/processos/{id}` — atualizar
- `DELETE /api/processos/{id}` — deletar
- `GET /api/processos` com filtros (tribunal, situacao, score_min, numero_cnj)

### ✅ 2.2 CRUD de Monitoramentos — RESOLVIDO
- `GET /api/monitoramentos` — listar
- `POST /api/monitoramentos` — criar
- `DELETE /api/monitoramentos/{id}` — deletar
- `PATCH /api/monitoramentos/{id}/ativar` — ativar/desativar

### ✅ 2.3 CRUD de Prazos — RESOLVIDO
- `GET /api/prazos` com filtros (cumprido, processo_id)
- `POST /api/prazos` — criar
- `PUT /api/prazos/{id}` — atualizar
- `DELETE /api/prazos/{id}` — deletar
- `PATCH /api/prazos/{id}/cumprir` — marcar cumprido

### ✅ 2.4 Gestão de Notificações — RESOLVIDO
- `PATCH /api/notificacoes/{id}/lida` — marcar como lida
- `POST /api/notificacoes/marcar_todas_lidas` — marcar todas
- `DELETE /api/notificacoes/{id}` — deletar

### ✅ 2.5 AdvogadoCatalog — RESOLVIDO
- `AdvogadoCatalog` agora é populado automaticamente ao salvar processo
- Cross-reference advogado-cliente via `advogado_de_id`
- `GET /api/advogados` — buscar advogados
- `GET /api/advogados/{oab}/{uf}` — detalhes

### ✅ 2.6 Partes/Movimentações em `/buscar/oab` — RESOLVIDO
Agora `/buscar/oab` retorna:
- `partes` completas (nome, tipo, polo, documento, oab)
- `movimentacoes` completas (data, descricao, tipo, categoria, impacto)
- `assunto`, `data_distribuicao`, `notas_auditoria`, `segredo_justica`

### ✅ 2.7 Filtros em `GET /api/processos` — RESOLVIDO
Agora aceita: `tribunal`, `situacao`, `score_min`, `numero_cnj`

---

## 3. 🟡 Problemas REMANESCENTES

### 3.1 AI Parser Não Gera Score de Auditoria
O `ai_parser.py` existe (434 linhas) mas **não há código que o invoque**. O score é calculado no `orquestrador.py` com regras fixas.

### 3.2 Dashboard É HTML Hardcoded
O dashboard em `main.py` retorna HTML hardcoded de ~2000 linhas.

### 3.3 ProJudi Tem TODO Aberto
```python
# src/crawlers/projudi.py:54
# TODO: Implementar fluxo de busca pública
```

### 3.4 PJe Detail Parsing Tem TODO Aberto
```python
# src/crawlers/pje.py:296
# TODO: Implementar _parse_detalhe_html para PJe
```

### 3.5 `comarca` Não é Extraída
Nenhum crawler popula o campo `comarca`.

### 3.6 `grau` Quase Nunca é Extraído
Embora o DataJud retorne, a maioria dos crawlers não extrai.

---

## 4. 🟡 Problemas de Segurança REMANESCENTES

### 4.1 Rate Limit Só em `/login`
Os endpoints `/register` e `/refresh` não têm rate limit.

### 4.2 Sem Rate Limit Global
Não há rate limit global, só por endpoint.

### 4.3 Credenciais de Tenant São bcrypt+texto
`TenantCredencial.api_secret` é texto legível.

### 4.4 Sem Autenticação em `/api/buscar/oab`
Qualquer pessoa pode fazer scraping massivo.

---

## 5. 📊 Tabela Comparativa: ANTES x DEPOIS

| Feature | Antes | Depois |
|---------|-------|--------|
| CRUD Processos | ❌ | ✅ |
| CRUD Monitoramentos | ❌ | ✅ |
| CRUD Prazos | ❌ | ✅ |
| Gestão Notificações | ❌ | ✅ |
| Catálogo Advogados | ❌ | ✅ |
| Partes em /buscar/oab | ❌ parcial | ✅ completo |
| Movimentações em /buscar/oab | ❌ parcial | ✅ completo |
| Filtros em /api/processos | ❌ | ✅ |
| Busca por advogado | ❌ | ✅ |
| **Nota Funcionalidade** | **5.5/10** | **7.5/10** |

---

## 6. 📋 Checklist de Melhorias REMANESCENTES

### Prioridade 🟡 MÉDIA
- [ ] Completar crawler ProJudi
- [ ] Completar parsing de detalhe PJe
- [ ] Extrair `comarca` nos crawlers
- [ ] Extrair `grau` nos crawlers
- [ ] AI Parser como fallback para score

### Prioridade 🟢 BAIXA
- [ ] Dashboard SPA em vez de HTML hardcoded
- [ ] Rate limit global
- [ ] Rate limit em `/register` e `/refresh`
- [ ] Credenciais de API com hash
- [ ] Autenticação em `/api/buscar/oab`

---

## 7. Tamanho e Complexidade

| Métrica | Valor |
|---------|-------|
| Total de linhas Python | ~9.300 |
| API endpoints | 35+ endpoints |
| Crawlers | 14 arquivos |
| migrations SQL | 6 arquivos |
| Models | 11 tabelas |

---

## 8. Conclusão

O projeto agora tem **gestão completa via API**. As principais lacunas funcionais foram resolvidas:

✅ CRUD de processos, monitoramentos, prazos
✅ Respostas completas com partes e movimentações
✅ Catálogo de advogados com cross-reference
✅ Gestão de notificações

**Falta resolver:** ProJudi/PJe incompletos, dashboard hardcoded, e alguns security gaps.


O sistema é um bom **motor de extração** mas precisa de uma **camada de gestão** para ser um produto completo.
