# Bloco 1: Persistência em PostgreSQL

## Visão Geral

Bloco 1 implementa a camada de persistência que:
1. **Salva processos** em PostgreSQL (tabela `processos`)
2. **Detalha partes** (pessoas físicas/jurídicas) em `partes`
3. **Registra movimentações** (eventos judiciais) em `movimentacoes`
4. **Detecta novas movimentações** via hash SHA-256 para evitar duplicatas
5. **Rastreia monitoramento** para Bloco 2 (scheduler diário)

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│  scripts/testar_oab_361329.py (MAIN)                    │
│  - Executa 7 crawlers (TJSP, PJe, TST, TRF3, eSAJ, etc) │
│  - Dedup por número CNJ                                 │
│  - NOVO: Chama ProcessoService.salvar_processos()       │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  src/services/processo_service.py (NEW)                 │
│  - ProcessoService.salvar_processos() — batch save      │
│  - ProcessoService.salvar_processo()  — single save     │
│  - Detecta novas movimentações via _hash_movimentacao() │
│  - Atualiza ultima_movimentacao_data automaticamente    │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│  PostgreSQL Database                                    │
│  ├─ processos          (39 TJSP processos)              │
│  ├─ partes            (autores, réus, advogados)        │
│  ├─ movimentacoes     (eventos judiciais)               │
│  ├─ monitoramentos    (para Bloco 2 scheduler)          │
│  ├─ notificacoes      (para Bloco 3 prazos)             │
│  └─ prazos            (para Bloco 3 deadline tracking)  │
└─────────────────────────────────────────────────────────┘
```

## Como Usar

### 1. Iniciar PostgreSQL

**Opção A: Docker (recomendado)**

```bash
docker-compose up -d db
# ou apenas o serviço PostgreSQL
docker-compose up -d db
```

**Opção B: PostgreSQL local instalado**

```bash
# Em Ubuntu/Debian
sudo service postgresql start

# Em macOS (via Homebrew)
brew services start postgresql

# Windows: Use pgAdmin ou SQL Shell
```

### 2. Verificar conexão

```bash
python -c "
import asyncio
from src.database.connection import engine
from sqlalchemy import text

async def test():
    async with engine.begin() as conn:
        await conn.execute(text('SELECT 1'))
    print('✓ PostgreSQL conectado')

asyncio.run(test())
"
```

### 3. Executar teste com persistência

```bash
# TJSP apenas (mais rápido, 39 processos):
OAB_SOMENTE_TJSP=1 python scripts/testar_oab_361329.py

# Todos os tribunais (mais lento, testa DataJud):
python scripts/testar_oab_361329.py
```

## Saída Esperada

```
→ Minerando OAB 361329/SP
→ Modo: apenas TJSP

  [1/7] TJSP eSAJ...
         → 39 processo(s)
  (pulando PJe/TST/TRF/eSAJ/STJ — modo TJSP only)

======================================================================
RESULTADO — OAB 361329/SP
======================================================================
Total processos únicos:    39
  com partes extraídas:    39 (100%)
  com advogados extraídos: 39 (100%)
  com valor da causa:      12 (30%)
  em segredo de justiça:   0

Por sistema:
  tjsp                   39

Por tribunal:
  tjsp                  39

Amostra (primeiros 10):
  [tjsp  ] 0000000-92.2019.8.26.0100
       autor=['MARIA APARECIDA CARDOSO DIAS']  réu=['BANCO BRADESCO S.A.']
       valor=R$ 15.000,00  partes=2  advogados=1
       advs=['GUSTAVO PELICIONI (361329)']
  ...

✓ Completo:         tests/resultado_oab_361329.json
✓ Segredo justiça:  tests/resultado_oab_361329_segredo.json

======================================================================
PERSISTÊNCIA EM POSTGRESQL
======================================================================
✓ Banco de dados:
  Total processados:       39
  Novos:                   39
  Atualizados:             0
  Movimentações novas:     XXX (total de eventos judiciais)
```

## API da ProcessoService

### Salvando um único processo

```python
from src.services.processo_service import ProcessoService
from src.database.connection import AsyncSessionLocal
from src.parsers.estruturas import ProcessoCompleto

async def exemplo():
    async with AsyncSessionLocal() as db:
        service = ProcessoService(db)
        
        # processo: ProcessoCompleto (vem do crawler)
        processo_db, hashes_novos = await service.salvar_processo(
            processo,
            criar_monitoramento=True,
            notificar_email="cartorio@escritorio.com.br"
        )
        
        print(f"ID: {processo_db.id}")
        print(f"Novas movimentações: {len(hashes_novos)}")
```

### Salvando múltiplos processos (batch)

```python
stats = await service.salvar_processos(
    processos=[p1, p2, p3, ...],
    criar_monitoramento=False,
)

print(f"Total: {stats['total']}")
print(f"Novos: {stats['novos']}")
print(f"Atualizados: {stats['atualizados']}")
print(f"Novas movimentações: {stats['movimentacoes_novas_total']}")
if stats['erros']:
    for erro in stats['erros']:
        print(f"  Erro: {erro}")
```

## Tabelas do PostgreSQL

### processos
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INT PK | Auto-incrementado |
| `numero_cnj` | VARCHAR(30) UNIQUE | Identificador único do processo |
| `tribunal` | VARCHAR(20) | tjsp, trf3, pje, tst, etc. |
| `grau` | VARCHAR(30) | G1, G2, RECURSAL, ORIGINARIO |
| `vara` | VARCHAR(200) | Ex: "1ª Vara Cível" |
| `comarca` | VARCHAR(200) | Ex: "São Paulo" |
| `classe_processual` | VARCHAR(200) | Tipo: Ação trabalhista, Busca e apreensão, etc |
| `assunto` | VARCHAR(500) | Tópico: Responsabilidade civil, Indenização, etc |
| `valor_causa` | NUMERIC(15,2) | Valor em R$ |
| `data_distribuicao` | DATE | Quando foi aberto |
| `situacao` | VARCHAR(100) | Em tramitação, Arquivado, etc |
| `segredo_justica` | BOOLEAN | true se processo é sigiloso |
| `observacoes` | TEXT | Anotações livres (ex: "segredo de justiça até 01/01/2025") |
| `ultima_movimentacao_data` | DATE | Atualizado automaticamente |
| `criado_em` | TIMESTAMP | Quando foi inserido |
| `atualizado_em` | TIMESTAMP | Quando foi atualizado |

### partes
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INT PK | Auto-incrementado |
| `processo_id` | INT FK | Referência a processos |
| `tipo_parte` | VARCHAR(50) | AUTOR, RÉU, ADVOGADO, etc |
| `nome` | VARCHAR(300) | Nome completo/razão social |
| `documento` | VARCHAR(20) | CPF ou CNPJ |
| `oab` | VARCHAR(20) | Número OAB (ex: 361329) |
| `polo` | VARCHAR(10) | ATIVO (autor) ou PASSIVO (réu) |
| `criado_em` | TIMESTAMP | Quando foi inserido |

### movimentacoes
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INT PK | Auto-incrementado |
| `processo_id` | INT FK | Referência a processos |
| `data_movimentacao` | DATE | Quando ocorreu o evento |
| `tipo` | VARCHAR(200) | "Sentença", "Apelação", "Pauta de audiência", etc |
| `descricao` | TEXT | Descrição completa do evento |
| `complemento` | TEXT | Informações adicionais |
| `codigo_nacional` | INT | Código nacional da movimentação (CNJ) |
| `categoria` | VARCHAR(50) | Categoria automática (útil para Bloco 3) |
| `impacto` | VARCHAR(20) | DECISORIO, COMUNICATIVO, DECISORIO_COM_EFEITO, etc |
| `criado_em` | TIMESTAMP | Quando foi inserido |

**Índices de performance:**
- `ix_movimentacoes_processo_data` — (processo_id, data_movimentacao) para queries rápidas de histórico

### monitoramentos
| Campo | Tipo | Descrição |
|-------|------|-----------|
| `id` | INT PK | Auto-incrementado |
| `processo_id` | INT FK | Referência a processos |
| `ativo` | BOOLEAN | Se deve ser monitorado (Bloco 2) |
| `ultima_verificacao` | TIMESTAMP | Quando foi checado pela última vez |
| `proxima_verificacao` | TIMESTAMP | Próxima execução do scheduler |
| `notificar_email` | VARCHAR(200) | Email para notificações (Bloco 3) |
| `webhook_url` | VARCHAR(500) | URL para webhook (futuro) |
| `criado_em` | TIMESTAMP | Quando foi inserido |

## Queries Úteis

### Ver todos os processos salvos
```sql
SELECT numero_cnj, tribunal, valor_causa, ultima_movimentacao_data
FROM processos
ORDER BY data_distribuicao DESC;
```

### Ver processos por OAB
```sql
SELECT DISTINCT p.numero_cnj, p.tribunal
FROM processos p
JOIN partes pt ON p.id = pt.processo_id
WHERE pt.tipo_parte = 'ADVOGADO' AND pt.oab = '361329'
ORDER BY p.data_distribuicao DESC;
```

### Ver últimas movimentações
```sql
SELECT p.numero_cnj, m.data_movimentacao, m.tipo, m.descricao
FROM movimentacoes m
JOIN processos p ON m.processo_id = p.id
ORDER BY m.data_movimentacao DESC
LIMIT 20;
```

### Processos em monitoramento
```sql
SELECT p.numero_cnj, p.tribunal, m.ativo, m.notificar_email
FROM processos p
JOIN monitoramentos m ON p.id = m.processo_id
WHERE m.ativo = true
ORDER BY m.ultima_verificacao;
```

## Próximos Passos (Blocos 2 e 3)

### Bloco 2: Scheduler Diário (2-3 dias)
- Executar `scripts/testar_oab_361329.py` automaticamente a cada 24h
- Comparar movimentações novas com histórico via hash
- Atualizar `monitoramentos.ultima_verificacao` e `proxima_verificacao`
- Criar registros em `notificacoes` quando há mudanças

### Bloco 3: Motor de Prazos (3-5 dias)
- Detectar tipos de movimentação: `categoria` + `impacto`
- Calcular `data_vencimento` baseado no tipo de prazo (15 dias para contestação, etc)
- Enviar email quando `data_vencimento` está próxima
- Marcar prazos como `cumprido` quando há movimento relevante

## Troubleshooting

### Erro: "connect call failed"
```
ConnectionRefusedError: [Errno 111] Connect call failed ('127.0.0.1', 5432)
```
→ PostgreSQL não está rodando. Execute `docker-compose up -d db`

### Erro: "FATAL: database 'juridico_crawler' does not exist"
```
psycopg2.OperationalError: FATAL:  database "juridico_crawler" does not exist
```
→ Banco ainda não foi criado. Docker-compose cria automaticamente.

### Erro de migração: "Table 'processos' already exists"
→ Já rodou create_tables(). OK, é idempotente.

### Erro: "violates unique constraint 'processos_numero_cnj_key'"
→ Processo já existe no DB. ProcessoService faz upsert automaticamente.

## Arquivos Criados/Modificados

**Novos:**
- `src/services/__init__.py`
- `src/services/processo_service.py` — Serviço principal

**Modificados:**
- `scripts/testar_oab_361329.py` — Adiciona chamada a `salvar_processos()` no final

**Já Existentes (não mudados):**
- `src/database/models.py` — ORM (Processo, Parte, Movimentacao, etc)
- `src/database/connection.py` — Pool de conexões async
- `src/database/migrations/001_initial.sql` — Schema PostgreSQL
