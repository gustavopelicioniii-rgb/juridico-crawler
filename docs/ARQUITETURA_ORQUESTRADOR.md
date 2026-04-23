# Arquitetura do Orquestrador Nativo

## Visão Geral

O `OrquestradorNativo` é o motor de busca parallelizada que distribui consultas de OAB para múltiplos tribunais brasileiros simultaneamente, usando os scrapers nativos de cada tribunal.

**Localização:** `src/crawlers/orquestrador.py`

## Fluxo de Execução

```
buscar_por_oab(numero_oab, uf_oab, tribunais?)
         │
         ▼
┌─────────────────────────────────────┐
│ 1. Normalizar lista de tribunais    │
│    - Se vazia → assume "todos"      │
│    - Se "todos" → varredura completa│
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ 2. Categorizar por tipo de crawler   │
│    TJSP │ TJMG │ eSAJ │ PJe │      │
│    eProc │ TRF │ STJ │ TST          │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ 3. Execução paralela com asyncio    │
│    asyncio.gather(return_exceptions) │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ 4. Coletar resultados + isolar      │
│    falhas (return_exceptions=True)   │
└─────────────────┬───────────────────┘
                  │
                  ▼
┌─────────────────────────────────────┐
│ 5. Deduplicar por CNJ              │
│ 6. Filtrar por advogado (opcional) │
│ 7. Retornar lista de Processos     │
└─────────────────────────────────────┘
```

## Categorização de Tribunais

| Alias | Crawler | Tribunais |
|-------|---------|-----------|
| `tjsp` | `TJSPCrawler` | TJSP |
| `tjmg` | `TJMG_UnifiedCrawler` | TJMG |
| `stj` | `STJCrawler` | STJ |
| `tst` | `TSTCrawler` | TST |
| `trf1-5` | `TRFCrawler` | TRF1 ao TRF5 |
| eSAJ | `ESajMultiCrawler` | TJXX (genérico) |
| PJe | `PJeCrawler` | Tribunais PJe |
| eProc | `EProcCrawler` | TRF4, TRT4, TJRO, TJAC |

## Parâmetros

```python
async def buscar_por_oab(
    numero_oab: str,              # Número da OAB (ex: "361329")
    uf_oab: str,                  # UF da OAB (ex: "SP")
    tribunais: list[str] = None,  # Lista de tribunais ou None/"todos"
    max_concorrentes_orquestrador: int = 5,  # Máximo de tarefas paralelas
    nome_advogado: str = None,    # Filtro opcional por nome
    cpf_advogado: str = None,     # Filtro opcional por CPF
) -> list[ProcessoCompleto]
```

## Execução Paralela

```python
# Exemplo simplificado
tasks = []
for tribunal in alvos:
    if tribunal == "tjsp":
        tasks.append(tjsp_crawler.buscar_por_oab(...))
    # ...

resultados = await asyncio.gather(*tasks, return_exceptions=True)
```

- **`return_exceptions=True`**: Se um crawler falhar, a exceção é retornada em vez de interromper toda a operação
- **`max_concorrentes_orquestrador=5`**: Limita o número de crawlers executando simultaneamente para evitar sobrecarga

## Deduplicação

Após coletar os resultados de todos os crawlers:

```python
# Dicionário para deduplicar por CNJ
processos_unicos = {}
for proc in todos_resultados:
    if isinstance(proc, Exception):
        logger.warning(f"Crawler falhou: {proc}")
        continue
    if proc.numero_cnj not in processos_unicos:
        processos_unicos[proc.numero_cnj] = proc
```

## Filtros de Precisão

Após a deduplicação, se `nome_advogado` ou `cpf_advogado` forem fornecidos:

```python
if nome_advogado:
    processos_unicos = {
        cnj: p for cnj, p in processos_unicos.items()
        if any(nome_advogado.lower() in p.nome_advogado.lower()
               for p in p.advogados)
    }
```

## Retorno

```python
return list(processos_unicos.values())
```

## Estrutura de Dados: ProcessoCompleto

```python
@dataclass
class ProcessoCompleto:
    numero_cnj: str
    tribunal: str
    vara: str
    classe_processual: str
    assunto: str
    situacao: str
    data_distribuicao: date
    valor_causa: Decimal
    partes: list[Parte]
    advogados: list[Advogado]
    movimentacoes: list[Movimentacao]
    ultimo_acao: str
    score_auditoria: int  # 0-100
    notas_auditoria: str
```

## Score de Auditoria

Cada processo recebe um score de 0-100 baseado na completude dos dados extraídos:

| Score | Qualificação |
|-------|--------------|
| 90-100 | Excelente — dados completos |
| 70-89 | Bom — dados principais presentes |
| 50-69 | Regular — dados parciais |
| 0-49 | Ruim — dados incompletos ou confiança baixa |

## Logging

O orquestrador usa `structlog` para logging estruturado:

```python
logger.info("Tribunais não especificados. Varredura completa.")
logger.info(f"Orquestrador Iniciando varredura para OAB {numero_oab}/{uf_oab}...")
logger.warning(f"Tribunal {t} não suportado ainda por um motor nativo.")
logger.error(f"Erro TJSP: {e}")
```
