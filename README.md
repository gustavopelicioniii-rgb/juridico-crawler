# Juridico Crawler

Sistema de crawling jurídico que consulta processos no DataJud (API oficial do CNJ) e tribunais brasileiros, extrai partes, advogados, datas e movimentações, e expõe via API REST.

## Funcionalidades

- **DataJud CNJ**: Consulta via API pública oficial (sem cadastro)
- **TJSP**: Scraping do sistema eSaj
- **PJe**: Suporte genérico ao sistema PJe
- **AI Parser**: Extração inteligente de dados via Claude (Anthropic)
- **Monitoramento**: Atualização automática diária de processos
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
uvicorn src.main:app --reload
```

## API Endpoints

### Processos

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/processos/buscar` | Busca processo por número CNJ |
| `GET` | `/processos/{numero_cnj}` | Retorna processo do banco |
| `GET` | `/processos/` | Lista processos com filtros |
| `DELETE` | `/processos/{id}` | Remove processo |

### Partes

| Método | Rota | Descrição |
|--------|------|-----------|
| `GET` | `/partes/processo/{processo_id}` | Lista partes de um processo |
| `GET` | `/partes/buscar?nome=...` | Busca por nome |
| `GET` | `/partes/buscar?oab=...` | Busca por OAB |

### Monitoramento

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/monitoramento/` | Ativa monitoramento de processo |
| `GET` | `/monitoramento/` | Lista monitoramentos ativos |
| `DELETE` | `/monitoramento/{id}` | Remove monitoramento |

## Exemplo de Uso

```bash
# Buscar e indexar um processo
curl -X POST "http://localhost:8000/processos/buscar" \
  -H "Content-Type: application/json" \
  -d '{"numero_cnj": "0001234-56.2024.8.26.0001", "tribunal": "tjsp"}'

# Consultar partes
curl "http://localhost:8000/partes/processo/1"

# Buscar advogado por OAB
curl "http://localhost:8000/partes/buscar?oab=123456SP"
```

## Tribunais Suportados

O sistema suporta 90+ tribunais via DataJud. Os principais:

- **TJSP** - Tribunal de Justiça de São Paulo
- **TJRJ** - Tribunal de Justiça do Rio de Janeiro
- **TRF1 a TRF6** - Tribunais Regionais Federais
- **TRT1 a TRT24** - Tribunais Regionais do Trabalho
- **STJ** - Superior Tribunal de Justiça
- **STF** - Supremo Tribunal Federal
- **TST** - Tribunal Superior do Trabalho

## Variáveis de Ambiente

| Variável | Descrição | Padrão |
|----------|-----------|--------|
| `DATABASE_URL` | URL do PostgreSQL | `postgresql+asyncpg://...` |
| `DATAJUD_API_KEY` | Chave pública CNJ | (incluída) |
| `ANTHROPIC_API_KEY` | Chave Claude API | *obrigatória* |
| `CRAWLER_REQUESTS_PER_MINUTE` | Rate limit | `30` |
| `SCHEDULER_CRON_HORA` | Hora do job diário | `2` |

## Licença

MIT
