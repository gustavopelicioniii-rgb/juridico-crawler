# Proxy Brasileiro para Tribunais

## Resumo

Alguns tribunais brasileiros **bloqueiam IPs de VPS estrangeiras** ou fazem rate limiting agressivo. Nesses casos, é necessário usar um **proxy residencial brasileiro**.

## Tribunais que PRECISAM de proxy

| Tribunal | Bloqueio | Proxy necessário? |
|----------|----------|-------------------|
| TJMG | 🔴 Alto | **SIM** |
| TJRJ | 🔴 Alto | **SIM** |
| TJPR | 🔴 Alto | **SIM** |
| TJSC | 🟡 Médio | Recomendado |
| TJRS | 🟡 Médio | Recomendado |
| TJDFT | 🟢 Baixo | Não |
| TJSP | 🟢 Estável | Não |
| TRT's (PJe) | 🟡 Médio | Às vezes |
| TRF's | 🟢 Estável | Não |
| STJ | 🟢 Estável | Não |
| TST | 🟢 Estável | Não |

## Proxies Recomendados

### 1. ProxyScrape (Mais Barato) ⭐
- **Preço**: ~$15-30/mês
- **Tipo**: Residential (IPs reais brasileiros)
- **Site**: https://proxyscrape.com
- **Formato**: `http://APIKEY-country-br:@ residential.proxyscrape.com:6060`

### 2. Oxylabs (Mais Confiável)
- **Preço**: ~$50-100/mês
- **Tipo**: Residential Premium
- **Site**: https://oxylabs.io
- **Formato**: `http://user:pass@br.oxylabs.io:7777`

### 3. Smartproxy
- **Preço**: ~$40-80/mês
- **Tipo**: Residential
- **Site**: https://smartproxy.com
- **Formato**: `http://user:pass@gate.smartproxy.com:7000`

## Como Configurar

### 1. Compre um proxy

Escolha um dos provedores acima. Depois de comprar, você receberá:
- **API Key** (ProxyScrape)
- Ou **usuário, senha, endpoint** (Oxylabs/Smartproxy)

### 2. Configure no .env

```bash
# ProxyScrape (residencial brasileiro):
PROXY_LIST=http://SUA_API_KEY-country-br:@residential.proxyscrape.com:6060

# Oxylabs:
PROXY_LIST=http://usuario:senha@br.oxylabs.io:7777

# Smartproxy:
PROXY_LIST=http://usuario:senha@gate.smartproxy.com:7000
```

### 3. Múltiplos proxies (recomendado pra produção)

```bash
# Round-robin entre vários proxies:
PROXY_LIST=http://user:pass@br1.proxy.com:8080,http://user:pass@br2.proxy.com:8080,http://user:pass@br3.proxy.com:8080
```

## Teste sem proxy primeiro

Antes de pagar por proxy, teste assim:

```bash
# Lista de tribunais sem proxy
python3 -c "
import asyncio
from src.crawlers.tjmg import TJMG_UnifiedCrawler

async def test():
    async with TJMG_UnifiedCrawler() as crawler:
        result = await crawler.buscar_por_oab('361329', 'SP')
        print(f'TJMG: {len(result)} processos')

asyncio.run(test())
"
```

Se der **bloqueio/captcha/erro 403**, aí sim você precisa de proxy.

## Oracle Cloud - Setup Grátis

### Passo 1: Criar conta
1. Acesse: https://www.oracle.com/cloud/free/
2. Escolha **Always Free** (não o paid)
3. Cadastre cartão de crédito (é obrigatório, mas NÃO cobra)

### Passo 2: Criar VM
1. **Compartment**:(root)
2. **Shape**: Ampere (ARM) - 4 cores, 24GB RAM
3. **Imagem**: Oracle Linux 8 ou Ubuntu 22.04
4. **Localidade**: São Paulo
5. **SSH Key**: Gere uma nova ou use existente

### Passo 3: Acessar e rodar
```bash
ssh -i sua_chave.pem opc@IP_DA_VM

# Baixar e rodar o setup:
curl -fsSL https://seu-dominio.com/setup_oracle_cloud.sh | bash
```

### Passo 4: Configurar
```bash
cd /opt/juridico-crawler
nano .env
# Configure ANTHROPIC_API_KEY
# Configure DATABASE_URL (já vem com PostgreSQL local)
```

### Passo 5: Iniciar
```bash
# Subir PostgreSQL
docker-compose up -d db

# Subir API
nohup uvicorn src.main:app --host 0.0.0.0 --port 8000 &
```

### Passo 6: Testar
```bash
curl http://localhost:8000/health
```

## IP Brasileiro

O IP da Oracle Cloud São Paulo **é brasileiro** e a maioria dos tribunais aceita.

Se mesmo assim algum tribunal bloquear:
1. Adicione proxy residencial
2. Ou use o serviço **Cloudflare Tunnel** pra expor a API

## FAQ

**P: Quanto tempo dura o free tier da Oracle?**
R: Para sempre, desde que você não exceda os limites.

**P: Precisa de cartão de crédito?**
R: Sim, mas só é cobrado se você升级 para paid.

**P: O IP da Oracle é limpo?**
R: Sim, IPs de data centers grandes geralmente são bem aceitos.

**P: Posso usar proxy do próprio Oracle?**
R: Não tem proxy nativo. Mas o IP do data center SP já é brasileiro.

---

## Custo Final Estimado (Produção)

| Item | Preço |
|------|-------|
| Oracle Cloud Free Tier | R$0 |
| Proxy (se precisar) | R$15-50/mês |
| API Claude (opcional) | R$5-30/mês |
| **Total** | **R$0-80/mês** |
