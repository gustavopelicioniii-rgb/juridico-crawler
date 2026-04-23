"""
Script para migrar dados do banco LOCAL para o banco da NUVEM (Railway).
Lê os processos locais e os envia via API para o Railway.
"""
import json
import urllib.request
import time

LOCAL = "http://127.0.0.1:8000"
CLOUD = "https://juridico-crawler-production.up.railway.app"

def get_json(url):
    req = urllib.request.Request(url)
    res = urllib.request.urlopen(req, timeout=30)
    return json.loads(res.read())

def post_json(url, data):
    payload = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    res = urllib.request.urlopen(req, timeout=60)
    return json.loads(res.read())

# ── 1. Pegar todos os processos do banco local ──
print("=" * 60)
print("ETAPA 1: Lendo processos do banco LOCAL...")
print("=" * 60)

local_data = get_json(f"{LOCAL}/api/integracao/processos?limit=1000")
processos = local_data["processos"]
print(f"✅ {len(processos)} processos encontrados no banco local.\n")

# ── 2. Enviar cada processo para o banco da nuvem ──
print("=" * 60)
print("ETAPA 2: Enviando processos para a NUVEM (Railway)...")
print("=" * 60)

# Precisamos de um endpoint que aceite dados por inserção direta
# Vamos usar a rota de extração por CNJ para cada processo
sucesso = 0
falha = 0

for i, p in enumerate(processos, 1):
    cnj = p["numero_cnj"]
    tribunal = p["tribunal"]
    print(f"  [{i}/{len(processos)}] {cnj} ({tribunal})... ", end="", flush=True)
    
    try:
        result = post_json(f"{CLOUD}/api/integracao/processo", {
            "numero_cnj": cnj,
            "tribunal": tribunal,
        })
        if result.get("status") == "ok":
            print(f"✅ ({result.get('novas_movimentacoes', 0)} movs)")
            sucesso += 1
        else:
            print(f"⚠️ {result.get('mensagem', 'sem detalhes')}")
            falha +=1
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if "404" in str(e.code):
            print("⏭️ DataJud offline para este CNJ")
        else:
            print(f"❌ HTTP {e.code}")
        falha += 1
    except Exception as e:
        print(f"❌ {e}")
        falha += 1
    
    # Pequena pausa para não sobrecarregar
    time.sleep(0.5)

print(f"\n{'=' * 60}")
print(f"RESULTADO FINAL")
print(f"  ✅ Sucesso: {sucesso}")
print(f"  ❌ Falha:   {falha}")
print(f"{'=' * 60}")

# ── 3. Verificar total na nuvem ──
cloud_total = get_json(f"{CLOUD}/api/processos/total")
print(f"\n📊 Total de processos na NUVEM agora: {cloud_total['total']}")
