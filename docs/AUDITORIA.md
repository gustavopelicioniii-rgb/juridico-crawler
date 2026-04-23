# Auditoria Completa — juridico-crawler

**Data:** 2026-04-23
**Repositório:** github.com/gustavopelicioniii-rgb/juridico-crawler
**Branch:** main · **Último commit:** fbd5dc6 (ci: fix railway login)

---

## 1. Visão Geral

**Tipo:** API REST em Python (FastAPI) para crawling de processos jurídicos brasileiros.

**Stack:**
- Python 3.12 + FastAPI 0.115 + Uvicorn
- SQLAlchemy 2.0 async + asyncpg + PostgreSQL 16
- Anthropic Claude (AI parser para extração de dados)
- APScheduler (jobs agendados)
- httpx + aiohttp (HTTP)
- BeautifulSoup + lxml + selectolax (HTML parsing)
- PyJWT + bcrypt (auth)
- Docker + docker-compose
- Railway deploy via GitHub Actions
- Dashboard separado em Express + HTML/Tailwind (porta 3333)

**O que faz:**
1. Recebe número de OAB/UF ou número CNJ
2. Distribui a busca em paralelo para 12+ scrapers nativos (TJSP, TJMG, PJe, eProc, eSAJ, TRF1-5, STJ, TST, etc.)
3. Consolida, deduplica e audita os processos coletados (score 0-100)
4. Persiste no PostgreSQL e expõe via REST + dashboard
5. Suporta multi-tenant (TenantAccount → TenantUser → JWT)

**Dimensão do código:**
- ~7.300 linhas em `src/`
- 12 crawlers (TJSP é o maior com 1019 linhas)
- 459 linhas no `main.py` (10 endpoints)
- 6 migrations SQL versionadas
- Dashboard frontend de 1662 linhas (HTML único)

---

## 2. 🔴 Problemas CRÍTICOS de Segurança

### 2.1 Token GitHub vazado no remote
```
origin  https://ghp_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX@github.com/...
```
Personal Access Token exposto no `.git/config`. **Revogar imediatamente** em github.com/settings/tokens e reconfigurar com SSH ou GH CLI.

### 2.2 JWT auth completamente quebrado
Em `src/api/auth.py:35`:
```python
async def get_current_user(
    authorization: Optional[str] = None,  # ❌ FastAPI nunca preenche isso
    session: AsyncSession = Depends(get_db),
):
```
Sem `Header(...)` ou `Security(...)`, a dependência **nunca recebe** o header `Authorization`. Todo endpoint que depende de `get_current_user` retorna 401 sempre. Correto:
```python
from fastapi import Header
async def get_current_user(
    authorization: str = Header(None),
    session: AsyncSession = Depends(get_db),
):
```

### 2.3 Endpoint de migrations público
`POST /api/migrations/run` em `main.py:333` **não tem autenticação**. Qualquer pessoa com acesso à API pode disparar migrations e quebrar a base.

### 2.4 SECRET_KEY com valor placeholder
`.env`:
```
API_SECRET_KEY=troque-por-uma-chave-segura-em-producao
```
Se essa string for usada para assinar JWTs em produção, qualquer um forja tokens.

### 2.5 Sem CORS configurado
`main.py` não importa nem usa `CORSMiddleware`. O dashboard (em outra porta/host) **não vai conseguir consumir a API** sem isso. Adicionar:
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
```

### 2.6 Vazamento de exceções na resposta
Em vários endpoints (`main.py:107, 135, 171, 207, 273, 321`):
```python
raise HTTPException(status_code=500, detail=str(e))
```
Isso expõe stack traces, paths, queries SQL etc. para o cliente. Logar internamente, devolver mensagem genérica.

### 2.7 Sem rate limiting
Endpoints de auth (`/login`, `/register`, `/refresh`) não têm proteção contra brute-force. Adicionar `slowapi` ou similar.

### 2.8 `verify_ssl=False` espalhado
Crawlers de PJe, eProc, TRF, STJ, TST, eSAJ desabilitam verificação SSL. **Por design** (proxies residenciais fazem MITM), mas precisa ficar explícito em documentação e idealmente só ativar quando proxy é detectado.

### 2.9 Migration endpoint quebra SQL complexo
`main.py:356`:
```python
for line in sql_content.split(';'):
```
Splitar SQL por `;` quebra functions, triggers, DO blocks. Use `sqlparse` ou execute o arquivo inteiro.

---

## 3. 🟡 Problemas de Qualidade & Higiene

### 3.1 Repositório poluído com arquivos de debug
~30+ scripts soltos na raiz do projeto:
```
auditor_robo.py, check_db.py, check_name.py, check_sidney.py,
check_specific_proc.py, check_statuses_sidney.py, compare_cnjs.py,
debug_db.py, debug_tjsp_links.py, debug_tjsp_pagination.py,
diag_mg.py, diagnostico_extremo.py, diagnostico_sidney_final.py,
diagnostico_sydney.py, executar_migration.py,
executar_migration_multi_tenant.py, inject_sidney_data.py,
inspect_html_tjsp.py, investigar_concluidos.py, investigar_pje.py,
load_test_50_oabs.py, migrar_para_cloud.py, stress_test_oab.py,
sync_cloud_to_local.py, test_cnj.py, test_imports.py,
testar_api.py, testar_oab_361329.py, teste_10_cnjs.py,
teste_10_oabs.py, teste_stress_auditoria.py,
trigger_railway.py, update_sidney.py, ...
```
Mover para `scripts/debug/`, `scripts/migrations/`, `scripts/load-test/`. A raiz vira "bancada de oficina" e ofusca o que realmente importa.

### 3.2 Arquivos pesados versionados
- `juridico.db` — 155 KB (SQLite local)
- `backup_local.sql` — 1.3 MB
- `tjsp_debug_pagination.html` — 112 KB
- `tjsp_oab_results_debug.html` — 109 KB

`.gitignore` cobre `*.db` e `backup_local.sql`, mas **já foram commitados** antes. Remover do tracking:
```bash
git rm --cached juridico.db backup_local.sql tjsp_debug_pagination.html tjsp_oab_results_debug.html
```

### 3.3 `.pyc` no repositório
Toda a árvore `src/__pycache__/` está versionada. Remover:
```bash
git rm -r --cached src/**/__pycache__
```

### 3.4 Arquivos `.OLD`
`src/main.py.OLD` — versão antiga do main. Apagar (git history preserva).

### 3.5 Working tree sujo
Arquivos modificados (cache `.pyc`) e untracked (`oabs_teste.txt`, `test_50_oabs.py`, `test_all_courts.py`). Decidir: limpar ou commitar.

### 3.6 Scheduler nunca inicia
`main.py:23`:
```python
scheduler = None
```
Variável criada mas nunca atribuída/iniciada. `src/scheduler/jobs.py` e `src/scheduler/scheduler_job.py` existem mas não são acionados no `lifespan`. **Funcionalidade prometida no README não está ativa.**

### 3.7 Tests fracos
- `pytest.ini` existe
- `tests/` tem 5 arquivos `test_*.py` reais
- Mas a raiz tem 15+ arquivos `test_*.py` que não são pytest tests, são scripts manuais
- Sem CI rodando testes (workflow só faz deploy)

### 3.8 Documentação fragmentada
12 arquivos `.md` na raiz: `BLOCO_1_PERSISTENCIA.md`, `BLOCO_2_SCHEDULER.md`, `BLOCO_3_MOTOR_DE_PRAZOS.md`, `DIA_2_*`, `DIA_3_*`, `MELHORIAS_IMPLEMENTADAS.md`, `WORKFLOW_COMPLETO.md`, etc. Parecem notas de desenvolvimento. Mover para `docs/` e consolidar.

---

## 4. 🟢 Pontos Fortes

1. **Stack moderna e bem escolhida** — FastAPI + async + SQLAlchemy 2.0 é exatamente o caminho certo para esse tipo de carga.
2. **Padrão Orquestrador Master** — `OrquestradorNativo` faz fan-out em paralelo via `asyncio.gather`, com `return_exceptions=True` para isolar falhas. Bem feito.
3. **Auditoria automática dos dados extraídos** — score 0-100 com notas explicativas (`p.score_auditoria`, `p.notas_auditoria`). Ajuda muito na qualidade do dataset.
4. **Deduplicação por CNJ** após consolidação multi-fonte.
5. **Filtros de precisão** por nome ou CPF do advogado (normalização de acentos, regex).
6. **Migrations versionadas** em SQL puro (6 arquivos numerados).
7. **Multi-tenant pronto** — `TenantAccount`, `TenantUser`, `TenantCredencial` modelados.
8. **Catálogo global de advogados** (`AdvogadoCatalog`) — feature inteligente de "auto-alimentação".
9. **Suporte a proxies residenciais** com round-robin (importante para TJs que bloqueiam IP internacional).
10. **Dashboard** com UI escura, animações, Chart.js — visual profissional.
11. **`.env.example` muito bem documentado** com instruções para cada provedor de proxy.
12. **Docker + Compose + Railway deploy** já configurados.

---

## 5. 🟠 Problemas Operacionais

### 5.1 Conflito entre `main.py` raiz e `src/main.py.OLD`
Confunde o leitor. Remover o `.OLD`.

### 5.2 Dashboard isolado
`dashboard/` é projeto Node separado, mas:
- `package-lock.json` na raiz (95 bytes — vazio?)
- Sem documentação de como integrar
- Sem variável de ambiente para apontar para a API
- Hardcoded `PORT = 3333`

### 5.3 README desatualizado
README cita endpoints `/processos/buscar` e `/partes/...` que **não existem** no `main.py`. Os reais são `/api/processos`, `/api/buscar/oab`, `/api/buscar/cnj`.

### 5.4 `TenantUser.tenant_email` index único
`models.py:212`: índice composto `tenant_id + email` único — bom. Mas e-mail isolado também tem index não-único, o que pode causar conflito de nomes.

### 5.5 Dependência implícita do AI Parser
README diz "Anthropic obrigatória", mas `buscar_por_cnj` em `main.py:293` chama com `usar_ai_parser=False`. Comportamento ambíguo.

### 5.6 Inglês + português misturados
Comentários, nomes de variáveis e docstrings alternam idiomas. Padronizar (sugiro PT-BR para o domínio jurídico, EN para infra).

### 5.7 Logging configurado mas estrutura inconsistente
`structlog` no requirements, mas `main.py` usa `logging` padrão e mistura `print()` no lifespan. Padronizar tudo em structlog.

---

## 6. 📋 Checklist de Próximos Passos (Recomendado)

### Urgência ALTA (segurança)
- [x] **Revogar token GitHub** vazado em `.git/config` (pendente - manual)
- [x] **Corrigir `get_current_user`** — `Header(None)` já presente
- [x] **Proteger `/api/migrations/run`** com `require_admin`
- [x] **Trocar `API_SECRET_KEY`** — validador adicionado em `src/config.py`
- [x] **Adicionar CORS middleware** — `CORSMiddleware` configurado
- [x] **Sanitizar mensagens de erro** — `logger.exception()` + mensagem genérica
- [x] **Rate limiting** — `slowapi` adicionado em `src/api/rate_limit.py`

### Urgência MÉDIA (higiene)
- [x] Remover `juridico.db`, `backup_local.sql`, `*_debug.html` do tracking
- [x] Remover `__pycache__/` do tracking (34 arquivos)
- [x] Mover scripts de debug para `scripts/debug/`
- [x] Apagar `src/main.py.OLD`
- [x] Consolidar `.md`s em `docs/`
- [x] Atualizar README com endpoints reais
- [x] Adicionar CI com pytest (`.github/workflows/ci.yml`)

### Urgência BAIXA (evolução)
- [x] Iniciar o scheduler de fato no `lifespan`
- [x] Usar `sqlparse` no endpoint de migrations
- [x] CI rodando pytest (workflow adicionado)
- [x] Migrar `logging` para `structlog` (20 módulos)
- [x] Documentar arquitetura do orquestrador (`docs/ARQUITETURA_ORQUESTRADOR.md`)
- [x] Rate limit global (100/min) + auth em /buscar/oab e /buscar/cnj (2026-04-23)
- [ ] Padronizar idioma (PT/EN mix - baixa prioridade)
- [ ] Hash de TenantCredencial.api_secret (requer re-issuance flow)

---

## 7. Resumo Executivo

| Aspecto | Nota | Observação |
|---|---|---|
| **Arquitetura** | 8/10 | Boa separação de camadas, padrão orquestrador inteligente |
| **Qualidade do código** | 7/10 | Débito técnico quitado; código mais limpo |
| **Segurança** | 8/10 | Rate limit global + auth em /buscar/* |
| **Documentação** | 8/10 | README atualizado; docs/ organizado |
| **Testes** | 4/10 | CI adicionado, cobertura ainda mínima |
| **DevOps** | 8/10 | Docker, Railway, GH Actions OK; CI adicionado |
| **NOTA GERAL** | **7,5/10** | **Pronto para produção após hardening de segurança** |
