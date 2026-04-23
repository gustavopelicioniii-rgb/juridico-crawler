# 📡 API REST Completa - Documentação

## 🚀 Iniciando a API

### Requisitos
```
FastAPI >= 0.100.0
uvicorn >= 0.23.0
SQLAlchemy >= 2.0
```

Já estão no `requirements.txt`!

### Iniciar Servidor

```bash
cd juridico-crawler

# Opção 1: Desenvolvimento
uvicorn main:app --reload

# Opção 2: Produção
uvicorn main:app --host 0.0.0.0 --port 8000

# Opção 3: Com workers
uvicorn main:app --workers 4 --host 0.0.0.0 --port 8000
```

### Acessar

- **Dashboard:** http://localhost:8000
- **Docs (Swagger):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/health

---

## 📋 Endpoints Completos

### 1️⃣ **PROCESSOS**

#### `GET /api/processos`
Lista todos os processos com paginação.

**Parâmetros:**
- `skip` (int, default=0) — Quantidade a pular
- `limit` (int, default=10, max=100) — Quantidade a retornar

**Exemplo:**
```bash
curl http://localhost:8000/api/processos?skip=0&limit=5
```

**Response:**
```json
[
  {
    "id": 1,
    "numero_cnj": "1504066-69.2025.8.26.0099",
    "tribunal": "TJSP",
    "classe_processual": "Ação Cível",
    "assunto": "Responsabilidade Civil",
    "valor_causa": 50000.00,
    "situacao": "Ativo",
    "ultima_movimentacao_data": "2026-04-08T17:49:59"
  }
]
```

---

#### `GET /api/processos/total`
Total de processos no banco.

**Response:**
```json
{
  "total": 39
}
```

---

#### `GET /api/processos/{processo_id}`
Detalhes de um processo específico.

**Exemplo:**
```bash
curl http://localhost:8000/api/processos/1
```

---

#### `GET /api/processos/{processo_id}/movimentacoes`
Movimentações de um processo.

**Parâmetros:**
- `limit` (int, default=10) — Quantidade de movs

**Response:**
```json
[
  {
    "id": 123,
    "data_movimentacao": "2026-04-08T10:00:00",
    "tipo": "CITAÇÃO",
    "descricao": "Citação do réu",
    "categoria": "PROCESSUAL"
  }
]
```

---

#### `POST /api/processos/{processo_id}/monitorar`
Ativa monitoramento para um processo.

**Body:**
```json
{
  "email": "escritorio@example.com",
  "webhook_url": "https://seu-servidor.com/webhook"  // opcional
}
```

**Response:**
```json
{
  "status": "ok",
  "mensagem": "Monitoramento ativado"
}
```

---

### 2️⃣ **NOTIFICAÇÕES**

#### `GET /api/notificacoes`
Lista todas as notificações.

**Parâmetros:**
- `skip` (int, default=0)
- `limit` (int, default=10)

**Response:**
```json
[
  {
    "id": 1,
    "tipo": "NOVA_MOVIMENTACAO",
    "resumo": "1 nova movimentação: Citação...",
    "lida": false,
    "criado_em": "2026-04-08T17:49:59"
  }
]
```

---

#### `GET /api/notificacoes/nao-lidas`
Apenas notificações não lidas.

**Response:**
```json
[
  {
    "id": 1,
    "tipo": "NOVA_MOVIMENTACAO",
    "resumo": "...",
    "lida": false,
    "criado_em": "..."
  }
]
```

---

#### `POST /api/notificacoes/{notif_id}/lida`
Marca notificação como lida.

**Example:**
```bash
curl -X POST http://localhost:8000/api/notificacoes/1/lida
```

---

#### `GET /api/notificacoes/stats`
Estatísticas de notificações.

**Response:**
```json
{
  "total": 45,
  "nao_lidas": 3,
  "lidas": 42
}
```

---

### 3️⃣ **PRAZOS**

#### `GET /api/prazos`
Lista todos os prazos.

**Parâmetros:**
- `skip` (int, default=0)
- `limit` (int, default=10)
- `apenas_abertos` (bool, default=true)

**Response:**
```json
[
  {
    "id": 1,
    "tipo_prazo": "CONTESTACAO",
    "descricao": "Contestação à ação",
    "data_inicio": "2026-04-08",
    "data_vencimento": "2026-04-30",
    "dias_uteis": 15,
    "cumprido": false
  }
]
```

---

#### `GET /api/prazos/vencendo`
Prazos que vencem em breve.

**Parâmetros:**
- `dias` (int, default=3) — Quantos dias antes avisar

**Response:**
```json
[
  {
    "id": 1,
    "tipo_prazo": "CONTESTACAO",
    "descricao": "Contestação à ação",
    "data_vencimento": "2026-04-11",
    "cumprido": false
  }
]
```

---

#### `GET /api/prazos/vencidos`
Prazos que venceram (não cumpridos).

---

#### `POST /api/prazos/{prazo_id}/cumprido`
Marca prazo como cumprido.

**Response:**
```json
{
  "status": "ok",
  "mensagem": "Prazo marcado como cumprido"
}
```

---

#### `GET /api/prazos/stats`
Estatísticas de prazos.

**Response:**
```json
{
  "total": 10,
  "cumpridos": 3,
  "abertos": 7
}
```

---

### 4️⃣ **SCHEDULER**

#### `POST /api/scheduler/execute`
Executa scheduler manualmente.

**Response:**
```json
{
  "status": "ok",
  "mensagem": "Scheduler executado com sucesso"
}
```

---

#### `GET /api/scheduler/status`
Status do scheduler.

**Response:**
```json
{
  "rodando": true,
  "ultima_verificacao": "2026-04-08T17:49:59",
  "proxima_verificacao": "2026-04-09T17:49:59"
}
```

---

### 5️⃣ **HEALTH**

#### `GET /health`
Health check da API.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-04-08T15:10:00",
  "scheduler": true
}
```

---

## 🎯 Dashboard Web

Acesse em: **http://localhost:8000**

**Features:**
- 📊 Resumo geral (processos, movs, notif, prazos)
- 📈 Estatísticas em tempo real
- 🔔 Últimas notificações
- ⏰ Prazos vencendo (3 dias)
- ▶️ Botão para executar scheduler manualmente
- 🔄 Auto-atualiza a cada 30s

---

## 📝 Exemplos de Uso

### 1. Listar Processos

```bash
curl http://localhost:8000/api/processos?limit=5
```

### 2. Ativar Monitoramento

```bash
curl -X POST http://localhost:8000/api/processos/1/monitorar \
  -H "Content-Type: application/json" \
  -d '{
    "email": "escritorio@example.com",
    "webhook_url": "https://meu-servidor.com/webhook"
  }'
```

### 3. Listar Prazos Vencendo

```bash
curl http://localhost:8000/api/prazos/vencendo?dias=3
```

### 4. Executar Scheduler Manualmente

```bash
curl -X POST http://localhost:8000/api/scheduler/execute
```

### 5. Marcar Notificação como Lida

```bash
curl -X POST http://localhost:8000/api/notificacoes/1/lida
```

---

## 🔐 Segurança

### Em Produção

```bash
# Com SSL
uvicorn main:app --ssl-keyfile=key.pem --ssl-certfile=cert.pem

# Com autenticação (recomendado)
# Adicionar Bearer token nos headers
```

### Adicionar Autenticação (Opcional)

```python
from fastapi.security import HTTPBearer, HTTPAuthCredentials

security = HTTPBearer()

@app.get("/api/processos")
async def listar_processos(credentials: HTTPAuthCredentials = Depends(security)):
    # Validar token aqui
    pass
```

---

## 📊 Integrações

### Slack

```python
import requests

def notificar_slack(mensagem):
    webhook_url = "https://hooks.slack.com/services/..."
    requests.post(webhook_url, json={"text": mensagem})
```

### Email

```python
from fastapi_mail import FastMail, MessageSchema

async def enviar_email(to: str, subject: str, body: str):
    message = MessageSchema(
        subject=subject,
        recipients=[to],
        body=body,
        subtype="html"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
```

---

## 🧪 Testando com Python

```python
import httpx

async def testar_api():
    async with httpx.AsyncClient() as client:
        # Listar processos
        resp = await client.get("http://localhost:8000/api/processos")
        print(resp.json())

        # Ativar monitoramento
        resp = await client.post(
            "http://localhost:8000/api/processos/1/monitorar",
            json={"email": "test@example.com"}
        )
        print(resp.json())

        # Executar scheduler
        resp = await client.post("http://localhost:8000/api/scheduler/execute")
        print(resp.json())
```

---

## 📈 Performance

| Endpoint | Tempo |
|----------|-------|
| GET /api/processos | ~50ms |
| GET /api/notificacoes | ~100ms |
| GET /api/prazos | ~80ms |
| POST /api/scheduler/execute | ~5-10s |

---

## 🐛 Troubleshooting

### Erro: "Port 8000 already in use"

```bash
# Windows
netstat -ano | findstr :8000

# Linux
lsof -i :8000
```

Mude para outra porta:
```bash
uvicorn main:app --port 8001
```

### Erro: "ModuleNotFoundError"

```bash
pip install -r requirements.txt
```

### Scheduler não iniciando

```bash
# Verificar se PostgreSQL está rodando
docker-compose ps

# Iniciar se necessário
docker-compose up -d db
```

---

## 📚 Documentação Automática

FastAPI gera documentação automática:

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Use para testar endpoints diretamente!

---

**Data:** 2026-04-08  
**Status:** ✅ PRONTO PARA USAR
