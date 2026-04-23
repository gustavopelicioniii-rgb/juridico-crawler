# Auditoria Funcional Completa — juridico-crawler

**Data:** 2026-04-23
**Repositório:** github.com/gustavopelicioniii-rgb/juridico-crawler
**Commit:** 3191b24

---

## 1. Resumo Executivo

| Aspecto | Status | Nota |
|---------|--------|------|
| **Funcionalidade de Busca** | Parcialmente funcional | 6/10 |
| **CRUD de Processos** | Ausente | 2/10 |
| **Persistência de Dados** | Funcional | 8/10 |
| **Multi-Tenant Auth** | Funcional | 7/10 |
| **Monitoramento/Scheduler** | Funcional | 7/10 |
| **Dashboard** | Básico (HTML hardcoded) | 3/10 |
| **Cobertura de Tribunais** | Boa (14+ crawlers) | 8/10 |
| **Extração de Dados** | Boa (partes, movs, valores) | 7/10 |
| **Inteligência (AI Parser)** | Parcialmente implementada | 5/10 |
| **Testes** | Mínimos | 3/10 |

**NOTA GERAL FUNCIONALIDADE:** **5.5/10**

---

## 2. 🔴 Problemas CRÍTICOS Funcionais

### 2.1 Sem CRUD de Processos
A API **não permite** criar, atualizar ou deletar processos manualmente. Só existe leitura.

**O que falta:**
```python
POST   /api/processos              # Criar processo manualmente
PUT    /api/processos/{id}         # Atualizar processo
DELETE /api/processos/{id}         # Deletar processo
POST   /api/processos/{id}/partes  # Adicionar parte
POST   /api/processos/{id}/monitoramento  # Ativar monitoramento
DELETE /api/processos/{id}/monitoramento  # Desativar monitoramento
```

**Impacto:** Não é possível gerenciar processos manualmente — só busca automática.

### 2.2 Sem Endpoints para Monitoramento
O modelo `Monitoramento` existe mas não há endpoints para:
```python
POST   /api/monitoramentos         # Criar monitoramento
GET    /api/monitoramentos         # Listar monitoramentos
DELETE /api/monitoramentos/{id}    # Cancelar monitoramento
```

**Impacto:** Não é possível ativar monitoramento de processos via API.

### 2.3 Sem Endpoints para Prazos
```python
POST   /api/prazos                 # Criar prazo manual
PUT    /api/prazos/{id}           # Atualizar prazo
DELETE /api/prazos/{id}           # Deletar prazo
POST   /api/prazos/{id}/cumprir   # Marcar como cumprido
```

**Impacto:** Sistema de prazos existe no banco mas não pode ser gerenciado.

### 2.4 Sem Notificações Read/Crud
```python
PUT    /api/notificacoes/{id}/lida  # Marcar como lida
DELETE /api/notificacoes/{id}       # Deletar notificação
POST   /api/notificacoes/marcar_todas_lidas
```

**Impacto:** Notificações ficam órfãs no banco.

### 2.5 `AdvogadoCatalog` Nunca é Alimentado
O modelo `AdvogadoCatalog` (catálogo de advogados) está definido e tem service, mas **não existe código que o popule automaticamente** durante as buscas.

**Como deveria funcionar:** Cada vez que um crawler encontra um advogado (extraído de `ParteProcesso` com `tipo_parte=ADVOGADO`), deveria upsertar no `AdvogadoCatalog`.

---

## 3. 🟡 Problemas Médios Funcionais

### 3.1 Score de Advogados Não É Extraído
No TJSP, o crawler extrai advogados mas **não popula o campo `advogado_de_id`** na tabela `parte`, que faria o link entre advogado e cliente.

```python
# Em src/crawlers/tjsp.py, método de extração de partes
# Oadvogado está sendo extraído como ParteProcesso, mas nunca
# é cross-referenceado com o advogado do polo oposto
```

### 3.2 AI Parser Não Gera Score de Auditoria
O `ai_parser.py` existe (434 linhas) mas **não há código que o invoque** para gerar `score_auditoria` e `notas_auditoria`. O score é calculado manualmente no `orquestrador.py` com regras fixas.

**Melhoria:** Usar o AI Parser para análise mais inteligente da completude dos dados.

### 3.3 Dashboard É HTML Hardcoded
O dashboard em `main.py:487` retorna HTML hardcoded de 2018 linhas. Isso é:
- Difícil de manter
- Sem JavaScript dinâmico
- Não consome a própria API (deveria redirect para `/dashboard/`)

### 3.4 Sem Busca por Nome/CPF de Advogado
A API não permite:
```python
GET /api/advogados/buscar?nome=João%20Silva
GET /api/advogados/buscar?cpf=12345678900
GET /api/advogados/{oab}  # Detalhes de um advogado específico
```

### 3.5 Sem Dados de Partes na Resposta de `/api/buscar/oab`
O endpoint `buscar_por_oab` retorna apenas dados do processo, não inclui as `partes` nem `advogados` diretamente. As partes são salvas no banco mas **não retornadas na resposta** da API.

```python
# Resposta atual:
{
    "numero_cnj": "...",
    "tribunal": "...",
    "score_auditoria": 85,
    "partes": ???,  # FALTANDO
    "movimentacoes": ???  # FALTANDO
}
```

### 3.6 Sem Filtros na Listagem de Processos
`GET /api/processos` não aceita filtros por:
- `tribunal`
- `situacao`
- `data_distribuicao` (range)
- `score_auditoria` (min/max)

---

## 4. 🟠 Gaps de Extração de Dados

### 4.1 `comarca` Não é Extraída
O modelo `Processo` tem campo `comarca` mas **nenhum crawler o popula**.

### 4.2 `grau` Quase Nunca é Extraído
Embora o DataJud retorne `grau` (G1, G2, RECURSAL), a maioria dos crawlers não extrai.

### 4.3 `codigo_nacional` das Movimentações
O campo existe no modelo mas crawlers não preenchem (requer parsing do código CNJ padronizado).

### 4.4 ProJudi Tem TODO Aberto
```python
# src/crawlers/projudi.py:54
# TODO: Implementar fluxo de busca pública (geralmente via consultaPublica.do)
```
O crawler ProJudi está incompleto.

### 4.5 PJe Detail Parsing Tem TODO Aberto
```python
# src/crawlers/pje.py:296
# TODO: Implementar _parse_detalhe_html para PJe se houver necessidade frequente
```
Detalhe de processos PJe pode estar incompleto.

---

## 5. 🟡 Problemas de Segurança

### 5.1 Token GitHub Já Era (revisado)
O token `ghp_PfNugzp9lUe9OL...` estava no `.git/config`. **Recomendado revogar** em https://github.com/settings/tokens.

### 5.2 Rate Limit Só em `/login`
O `@limiter.limit("10/minute")` só está em `/login`. Dealers os endpoints de auth (`/refresh`, `/register`) também precisam.

### 5.3 Sem Rate Limit Global
Não há rate limit global, só por endpoint específico.

### 5.4 Credenciais de Tenant São bcrypt+texto
`TenantCredencial` armazena `api_secret` como texto legível no banco. Deveria ser hasheado como senhas.

### 5.5 Sem Expired Token Cleanup
Refresh tokens não têm TTL verificado no código — rely no JWT expiry.

### 5.6 Sem Autenticação em `/api/buscar/oab`
O endpoint de busca não requer autenticação. Qualquer pessoa pode fazer scraping massivo sem login.

### 5.7 CORS Permite Tudo em Dev
```python
allow_origins=settings.cors_origins  # Padrão: "http://localhost:3333,http://localhost:5173"
```
Em produção, isso precisa ser restrito.

---

## 6. 🟢 Pontos Funcionais Positivos

### 6.1 Arquitetura de Crawlers É Boa
- 14+ crawlers nativos implementados
- `OrquestradorNativo` com fan-out paralelo
- `return_exceptions=True` para isolamento de falhas
- Fallback para Firecrawl quando HTML é bloqueado

### 6.2 Deduplicação por CNJ
Funciona bem — mesma causa distribuída em tribunais diferentes é unificada.

### 6.3 Sistema de Score de Auditoria
O score 0-100 com notas é uma feature excelente para confiança dos dados.

### 6.4 Multi-Tenant Bem Modelado
`TenantAccount → TenantUser → TenantCredencial` com RLS pronto.

### 6.5 Monitoramento com Webhook
Notificações via webhook são bem implementadas.

### 6.6 Schema SQL versionado
6 arquivos de migration numerados, bem organizados.

---

## 7. 📊 Tabela Comparativa: Claimed vs Real

| Feature | README/API Claims | Implementado |
|---------|-------------------|-------------|
| Busca por OAB | ✅ | ✅ |
| Busca por CNJ | ✅ | ✅ |
| Partes (autor/réu) | ✅ | ✅ |
| Advogados | ✅ | ✅ Parcial (sem cross-link) |
| Movimentações | ✅ | ✅ |
| Valor da causa | ✅ | ✅ |
| Score auditoria | ❌ | ✅ |
| Monitoramento automático | ✅ | ✅ |
| Notificações | ✅ | ✅ (mas sem API de gestão) |
| Prazos | Mencionado | ✅ (mas sem API de gestão) |
| Dashboard | Mencionado | ⚠️ HTML hardcoded |
| Multi-tenant | ❌ | ✅ |
| CRUD de processos | ❌ | ❌ Ausente |
| Busca por advogado | ❌ | ❌ Ausente |

---

## 8. 📋 Checklist de Melhorias Prioritárias

### Prioridade 🔴 CRÍTICA
- [ ] Adicionar endpoints CRUD para processos
- [ ] Adicionar endpoints CRUD para monitoramentos
- [ ] Popular `AdvogadoCatalog` automaticamente
- [ ] Retornar `partes` e `movimentacoes` na resposta de `/api/buscar/oab`
- [ ] Corrigir extração de `advogado_de_id` para cross-reference advogado-parte

### Prioridade 🟡 MÉDIA
- [ ] Completar crawler ProJudi
- [ ] Completar parsing de detalhe PJe
- [ ] Extrair `comarca` nos crawlers
- [ ] Extrair `grau` nos crawlers
- [ ] Filtros em `GET /api/processos`
- [ ] Endpoints para gestão de prazos
- [ ] Marcar notificações como lidas
- [ ] AI Parser como fallback para score de auditoria

### Prioridade 🟢 BAIXA
- [ ] Dashboard SPA em vez de HTML hardcoded
- [ ] Busca por nome/CPF de advogado
- [ ] Rate limit global
- [ ] Rate limit em `/register` e `/refresh`
- [ ] Credenciais de API com hash
- [ ] Validação de CORS em produção

---

## 9. Tamanho e Complexidade

| Métrica | Valor |
|---------|-------|
| Total de linhas Python | ~8.224 |
| Crawlers | 14 arquivos |
| migrations SQL | 6 arquivos |
| Models | 11 tabelas |
| API endpoints | 11 endpoints |
| Coverage testes | ~15% (estimado) |

---

## 10. Conclusão

O projeto está **funcional para busca e extração de dados processuais**, mas falta **gestão completa via API**. A arquitetura de crawlers é robusta, mas faltam:

1. **CRUD completo** — não existe gestão de processos
2. **API de monitoramentos** — não existe gestão de alertas  
3. **Cross-reference advogado-parte** — advogados não são vinculados aos clientes
4. **Respostas completas** — `/buscar/oab` não retorna todos os dados extraídos
5. **Dashboard** — HTML hardcoded não é mantenível

O sistema é um bom **motor de extração** mas precisa de uma **camada de gestão** para ser um produto completo.
