# Juridico Crawler

Sistema de crawling jurídico que consulta processos no DataJud (API oficial do CNJ) e tribunais brasileiros, extrai partes, advogados, datas e movimentações, e expõe via API REST.

## Funcionalidades

- **DataJud CNJ**: Consulta via API pública oficial (sem cadastro)
- **TJSP**: Scraping do sistema eSaj (com suporte a OAB)
- **Multi-Tenant**: Múltiplas contas de escritório com isolamento
- **AI Parser**: Extração inteligente de dados via Claude (Anthropic)
- **Monitoramento**: Atualização automática diária de processos
- **Auditoria**: Score de qualidade 0-100 para cada extração
- **API REST**: Endpoints completos para consulta e gerenciamento

## Início Rápido

### Pré-requisitos
- Docker e Docker Compose
- Python 3.12+ (para desenvolvimento local)

### Com Docker

```bash
# 1. Copiar e configurar variáveis de ambiente
cp .env.example .env
# Editar .env com suas chaves (especialmente ANTHROPIC_API_KEY)

# 2. Subir os serviços
docker-compose up -d

# 3. Verificar
curl http://localhost:8000/health
```

### Desenvolvimento Local

```bash
# 1. Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# 2. Instalar dependências
pip install -r requirements.txt

# 3. Configurar .env
cp .env.example .env

# 4. Subir apenas o banco
docker-compose up -d db

# 5. Rodar a aplicação
uvicorn main:app --reload
```

## API Endpoints

### Autenticação

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `POST` | `/api/auth/login` | Login com email + senha | ❌ |
| `POST` | `/api/auth/refresh` | Renovar access token | ❌ |
| `POST` | `/api/auth/register` | Criar usuário (admin) | ✅ |
| `GET` | `/api/auth/me` | Dados do usuário | ✅ |
| `POST` | `/api/auth/change-password` | Alterar senha | ✅ |

### Processos

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `GET` | `/api/processos` | Lista processos (paginado) | ❌ |
| `GET` | `/api/processos/{id}` | Detalhes de processo | ❌ |
| `POST` | `/api/buscar/oab` | Busca por OAB + UF | ❌ |
| `GET` | `/api/buscar/cnj/{numero_cnj}` | Busca por CNJ (DataJud) | ❌ |

### Dados

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `GET` | `/api/notificacoes` | Lista notificações | ❌ |
| `GET` | `/api/prazos` | Lista prazos | ❌ |

### Sistema

| Método | Rota | Descrição | Auth |
|--------|------|-----------|------|
| `GET` | `/health` | Health check | ❌ |
| `POST` | `/api/migrations/run` | Executar migrations | ✅ Admin |

## Exemplo de Uso

```bash
# Login
curl -X POST "http://localhost:8000/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "usuario@email.com", "password": "senha", "tenant_numero_oab": "361329"}'

# Buscar por OAB (ex: 361329/SP)
curl -X POST "http://localhost:8000/api/buscar/oab" \
  -H "Content-Type: application/json" \
  -d '{"numero_oab": "361329", "uf_oab": "SP"}'

# Buscar por CNJ
curl "http://localhost:8000/api/buscar/cnj/0001234-56.2024.8.26.0001"

# Listar processos
curl "http://localhost:8000/api/processos?skip=0&limit=10"
```

## Tribunais Suportados (via scrapers nativos)

- **TJSP** - Tribunal de Justiça de São Paulo
- **TJMG** - Tribunal de Justiça de Minas Gerais
- **TJRJ** - Tribunal de Justiça do Rio de Janeiro
- **TRF1 a TRF6** - Tribunais Regionais Federais
- **TRT1 a TRT24** - Tribunais Regionais do Trabalho
- **STJ** - Superior Tribunal de Justiça
- **TST** - Tribunal Superior do Trabalho
- **eProc** - Sistema eProc (TRF4, TRT4, TJRO, TJAC)
- **PJe** - Sistema PJe (Suporte genérico)
- **eSAJ** - Sistema eSAJ (Genérico)
- **ProJudi** - Sistema ProJudi

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATABASE_URL` | URL do PostgreSQL | `postgresql+asyncpg://...` |
| `ANTHROPIC_API_KEY` | Chave Claude API | *obrigatória* |
| `DATAJUD_API_KEY` | Chave pública CNJ | (incluída) |
| `API_SECRET_KEY` | Chave para JWT | (mudar em prod) |
| `API_ENVIRONMENT` | `development` ou `production` | `development` |
| `FRONTEND_ORIGINS` | Origins permitidas para CORS | `localhost:3333` |
| `SCHEDULER_ENABLED` | Ativar scheduler | `true` |
| `SCHEDULER_CRON_HORA` | Hora do job diário | `2` |
| `CRAWLER_REQUESTS_PER_MINUTE` | Rate limit por tribunal | `30` |

## Documentação

- `docs/AUDITORIA.md` - Auditoria completa de segurança
- `docs/API_REST_DOCS.md` - Documentação da API REST
- `docs/BLOCO_1_PERSISTENCIA.md` - Arquitetura de persistência
- `docs/BLOCO_2_SCHEDULER.md` - Arquitetura do scheduler
- `docs/BLOCO_3_MOTOR_DE_PRAZOS.md` - Motor de prazos
- `docs/WORKFLOW_COMPLETO.md` - Workflow completo do sistema

## Licença

MIT
