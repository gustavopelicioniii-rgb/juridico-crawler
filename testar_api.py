import json, urllib.request

url = "https://juridico-crawler-production.up.railway.app"

# Teste 1: Endpoint COMPLETO (com partes e movimentações)
print("=" * 60)
print("ENDPOINT COMPLETO: /api/integracao/processos")
print("=" * 60)
r = urllib.request.urlopen(f"{url}/api/integracao/processos?limit=1", timeout=15)
data = json.loads(r.read())
p = data["processos"][0]
print(json.dumps(p, indent=2, ensure_ascii=False))

print("\n" + "=" * 60)
print("ENDPOINT SIMPLES: /api/processos")
print("=" * 60)
r2 = urllib.request.urlopen(f"{url}/api/processos?limit=1", timeout=15)
data2 = json.loads(r2.read())
print(json.dumps(data2[0], indent=2, ensure_ascii=False, default=str))
