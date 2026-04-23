# Workflow Completo: Bloco 1 + Bloco 2

## 🎯 Objetivo Final

Sistema que:
1. ✅ **Persiste processos em PostgreSQL** (Bloco 1)
2. ✅ **Monitora processos 24/7** e detecta novas movimentações (Bloco 2)
3. ➡️ **Detecta prazos** e envia lembretes (Bloco 3 — em desenvolvimento)

## 📊 Visão Geral do Fluxo

```
USER / CRAWLER
    ↓
┌───────────────────────────────────────┐
│  Bloco 1: PERSISTÊNCIA                │
│  ────────────────────────────         │
│  ProcessoService.salvar_processos()   │
│  └─ Upsert de processos               │
│  └─ Insert de partes                  │
│  └─ Insert de movimentações (hash)    │
│  └─ Update ultima_movimentacao_data   │
└───────────────┬───────────────────────┘
                ↓
        ✓ PostgreSQL
        (processos, partes, movimentacoes, 
         monitoramentos, notificacoes)
                ↓
    ┌───────────────────────────────────┐
    │ Bloco 2: SCHEDULER (24/7)         │
    │ ─────────────────────────────     │
    │ APScheduler (cada 24h)            │
    │ ├─ Re-executa crawlers            │
    │ ├─ Merge inteligente (dedup)      │
    │ ├─ Detecta novas movs             │
    │ ├─ Cria notificações              │
    │ └─ Envia webhooks                 │
    └─────────────────────────────────┘
```

## 🚀 Setup Passo a Passo

### Passo 1: Instalar Dependências

```bash
# Requirements já inclusos
pip install -r requirements.txt

# Principais packages para Bloco 1 + 2:
- sqlalchemy>=2.0
- asyncpg  # PostgreSQL async driver
- apscheduler  # Scheduler
- pydantic
```

### Passo 2: Configurar PostgreSQL

```bash
# Iniciar banco (via Docker)
docker-compose up -d db

# Aguardar 10-15s para database estar ready
sleep 15
```

### Passo 3: Executar Migration 004

```bash
# Setup inicial das tabelas Bloco 2
python executar_migration.py

# Output esperado:
# ✓ Migration 004 executada com sucesso!
# ✓ Todas as colunas adicionadas
```

### Passo 4: Popular Dados Iniciais (Bloco 1)

```bash
# Executar crawler + persistência (Bloco 1)
OAB_SOMENTE_TJSP=1 python scripts/testar_oab_361329.py

# Output esperado:
# ======================================================================
# PERSISTÊNCIA EM POSTGRESQL
# ======================================================================
# ✓ Banco de dados:
#   Total processados:       39
#   Novos:                   39
#   Atualizados:             0
#   Movimentações novas:     ~800
```

### Passo 5: Ativar Monitoramento (Bloco 2)

```python
# Script: ativar_monitoramento.py
import asyncio
from src.database.connection import AsyncSessionLocal
from src.database.models import Monitoramento, Processo
from sqlalchemy import select
from datetime import datetime

async def ativar_para_todos():
    """Ativa monitoramento para todos os processos."""
    async with AsyncSessionLocal() as db:
        # Busca todos os processos
        result = await db.execute(select(Processo))
        processos = result.scalars().all()
        
        print(f"Ativando monitoramento para {len(processos)} processos...")
        
        for p in processos:
            # Verifica se já tem monitoramento
            result = await db.execute(
                select(Monitoramento).where(
                    Monitoramento.processo_id == p.id
                )
            )
            mon = result.scalar_one_or_none()
            
            if not mon:
                # Cria novo monitoramento
                mon = Monitoramento(
                    processo_id=p.id,
                    ativo=True,
                    notificar_email="escritorio@example.com",
                    proxima_verificacao=datetime.now(),
                )
                db.add(mon)
        
        await db.commit()
        print(f"✓ Monitoramento ativado para {len(processos)} processos")

asyncio.run(ativar_para_todos())
```

Executar:
```bash
python ativar_monitoramento.py
```

### Passo 6: Iniciar Scheduler (Bloco 2)

**Opção A: Teste Único**
```bash
# Executa scheduler uma vez
python scripts/testar_scheduler.py

# Output:
# ======================================================================
# TESTE DO SCHEDULER
# ======================================================================
# ✓ Processos verificados:       39
# ✓ Com atualizações:            3
# ✓ Movimentações novas:         5
# ✓ Notificações criadas:        3
```

**Opção B: Modo Contínuo (via FastAPI)**

```python
# main.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from src.scheduler.jobs import criar_scheduler

scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global scheduler
    scheduler = criar_scheduler()
    scheduler.start()
    print("✓ Scheduler iniciado")
    yield
    # Shutdown
    scheduler.shutdown()
    print("✓ Scheduler parado")

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "scheduler": "rodando"}
```

Executar:
```bash
uvicorn main:app --reload
# Scheduler roda automaticamente em background
```

## 📋 Checklist de Execução

```
Bloco 1 - Persistência
  ✓ PostgreSQL rodando
  ✓ Migration 004 executada
  ✓ Scripts de crawler + persistência funcionando
  ✓ Dados iniciais carregados (39 processos)

Bloco 2 - Scheduler
  ✓ Monitoramentos criados para processos
  ✓ Tabelas notificacoes/prazos em PostgreSQL
  ✓ Scheduler iniciado
  ✓ APScheduler agendado para 02:00 AM diariamente
  ✓ Teste manual executado com sucesso
```

## 🔍 Verificação Rápida

### 1. Verificar Dados no PostgreSQL

```bash
# Processos cadastrados
psql -U postgres -d juridico_crawler -c \
  "SELECT COUNT(*) as total_processos FROM processos;"

# Movimentações cadastradas
psql -U postgres -d juridico_crawler -c \
  "SELECT COUNT(*) as total_movimentacoes FROM movimentacoes;"

# Monitoramentos ativos
psql -U postgres -d juridico_crawler -c \
  "SELECT COUNT(*) as monitorando FROM monitoramentos WHERE ativo=True;"

# Notificações criadas
psql -U postgres -d juridico_crawler -c \
  "SELECT COUNT(*) as notificacoes FROM notificacoes;"
```

### 2. Verificar Logs do Scheduler

```bash
# Ver logs recentes
tail -f /tmp/scheduler.log

# Ou usar query SQL
psql -U postgres -d juridico_crawler -c \
  "SELECT 
     p.numero_cnj,
     m.ultima_verificacao,
     m.proxima_verificacao,
     COUNT(n.id) as notificacoes_nao_lidas
   FROM monitoramentos m
   JOIN processos p ON m.processo_id = p.id
   LEFT JOIN notificacoes n ON n.processo_id = p.id AND n.lida = False
   GROUP BY p.numero_cnj, m.ultima_verificacao, m.proxima_verificacao
   ORDER BY m.ultima_verificacao DESC;"
```

### 3. Testar Detecção de Novas Movimentações

```python
# test_deteccao.py
import asyncio
from src.scheduler.jobs import atualizar_processos_monitorados

async def test():
    print("Executando detecção de novas movimentações...")
    await atualizar_processos_monitorados()
    print("✓ Teste concluído")

asyncio.run(test())
```

## 📊 Fluxo de Dados — Exemplo Real

### Cenário: Processo com OAB 361329

**Dia 1 — Inicial:**
```
1. Crawler extrai: 39 processos com ~800 movs total
2. ProcessoService.salvar_processos() → Insert no PostgreSQL
3. Monitoramento criado com ativo=True, proxima_verificacao=2026-04-09 02:00
```

**Dia 2 — 02:00 AM:**
```
1. Scheduler executa atualizar_processos_monitorados()
2. DataJudCrawler busca processo atualizado do tribunal
3. Tribunal retorna processo com 810 movs (10 novas)
4. Merge:
   - Compara (data, descricao[:100]) das 810 vs 800 existentes
   - Detecta 10 que não existem
   - INSERT 10 movs novas no banco
5. _notificar_novas_movimentacoes():
   - INSERT Notificacao(tipo="NOVA_MOVIMENTACAO", ...)
   - POST webhook com dados
   - Dispara callbacks
6. Update monitoramento:
   - ultima_verificacao = 2026-04-09 02:00
   - proxima_verificacao = 2026-04-10 02:00
```

**Resultado em PostgreSQL:**
```sql
-- Notificação criada
SELECT * FROM notificacoes 
WHERE processo_id = 1 
  AND criado_em >= '2026-04-09'::date
ORDER BY criado_em DESC;

-- Movs novas inseridas
SELECT * FROM movimentacoes 
WHERE processo_id = 1 
  AND data_movimentacao >= '2026-04-08'::date
ORDER BY data_movimentacao DESC;
```

## 🚨 Tratamento de Erros

### Cenário 1: Tribunal indisponível

```
2026-04-09 02:00 AM
├─ DataJudCrawler.buscar_processo()
│  └─ Exception: "Connection timeout"
│
└─ Exceção capturada em atualizar_processos_monitorados()
   ├─ Log: "Erro ao atualizar processo XXXX: Connection timeout"
   ├─ erros += 1
   └─ proxima_verificacao = agora + 6h (tenta novamente em 6h)
   
Resultado:
- Não bloqueia outros processos
- Próxima tentativa: 08:00 AM (não espera 24h)
```

### Cenário 2: Webhook offline

```
2026-04-09 02:00 AM
├─ Detectadas 5 novas movs
├─ Notificacao criada no banco ✓
├─ POST webhook_url
│  └─ Exception: "Connection refused"
│
└─ Log: "Webhook falhou para http://webhook.exemplo.com"
   
Resultado:
- Notificação continua no banco (lida=False)
- Próxima tentativa: próxima execução do scheduler
```

### Cenário 3: Novo processo (sem monitoramento)

```
Novo processo X é criado
├─ INSERT no banco ✓
├─ Scheduler procura Monitoramento.ativo=True
│  └─ Nenhum encontrado
└─ Processo ignorado na próxima execução

Solução:
- Ativar monitoramento via API/CLI
  POST /api/processos/{id}/monitorar
  └─ Cria Monitoramento, define proxima_verificacao=NOW()
- Próxima execução do scheduler: 20 minutos depois
```

## 🔗 Integração com Sistemas Externos

### Exemplo 1: Slack Notifications

```python
# slack_callback.py
import httpx

async def notificar_slack(payload: dict):
    """Callback para notificações via Slack."""
    webhook_slack = "https://hooks.slack.com/services/..."
    
    mensagem = f"""
    🚨 Processo atualizado: {payload['numero_cnj']}
    Tribunal: {payload['tribunal']}
    Novas movs: {payload['total_novas']}
    """
    
    async with httpx.AsyncClient() as client:
        await client.post(webhook_slack, json={"text": mensagem})

# Registrar callback
from src.scheduler.jobs import registrar_callback_notificacao
registrar_callback_notificacao(notificar_slack)
```

### Exemplo 2: WebSocket para Frontend

```python
# websocket_callback.py
async def notificar_websocket(payload: dict):
    """Callback para notificações via WebSocket."""
    from fastapi_broadcast import broadcast
    
    await broadcast.publish(
        channel="notificacoes",
        message={
            "tipo": "nova_movimentacao",
            "numero_cnj": payload['numero_cnj'],
            "total_novas": payload['total_novas'],
        }
    )

# Registrar
from src.scheduler.jobs import registrar_callback_notificacao
registrar_callback_notificacao(notificar_websocket)
```

## 📈 Monitoramento de Saúde

### Query: Saúde do Scheduler

```sql
-- Última execução de cada monitoramento
SELECT 
    p.numero_cnj,
    p.tribunal,
    m.ultima_verificacao,
    m.proxima_verificacao,
    CASE 
        WHEN m.proxima_verificacao < NOW() THEN '⚠️  ATRASADO'
        WHEN m.proxima_verificacao < NOW() + interval '6 hours' THEN '⏰ PRÓXIMO'
        ELSE '✓ OK'
    END as status
FROM monitoramentos m
JOIN processos p ON m.processo_id = p.id
WHERE m.ativo = True
ORDER BY m.proxima_verificacao ASC;
```

### Query: Taxa de Detecção

```sql
-- Quantas notificações por dia
SELECT 
    DATE(criado_em) as data,
    COUNT(*) as notificacoes,
    COUNT(DISTINCT processo_id) as processos_com_novidades
FROM notificacoes
WHERE tipo = 'NOVA_MOVIMENTACAO'
GROUP BY DATE(criado_em)
ORDER BY data DESC;
```

---

## 📚 Próximos Passos

### ➡️ Bloco 3: Motor de Prazos

Detectar e notificar prazos automaticamente:

```
Nova movimentação detectada
    ↓
PrazoService.detectar_prazos_por_movimentacao()
    ├─ Se tipo = "CITAÇÃO" → Cria Prazo(tipo="CONTESTACAO", dias=15)
    ├─ Se tipo = "SENTENÇA" → Cria Prazo(tipo="RECURSO", dias=15)
    └─ Se tipo = "APELAÇÃO" → Cria Prazo(tipo="CONTRARRAZÃO", dias=15)
    ↓
Scheduler verifica diariamente:
    - Prazos com data_vencimento - 3 dias = HOJE
    - Envia email: "Prazo de CONTESTAÇÃO vence em 3 dias"
    ↓
Quando movimento relevante chegar:
    - Mark Prazo.cumprido = True
    - Cria Notificacao(tipo="PRAZO_CUMPRIDO")
```

---

**Status:** ✅ Bloco 1 + Bloco 2 Completo | ➡️ Bloco 3 em Breve
