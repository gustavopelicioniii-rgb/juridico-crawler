"""
Verifica o mapeamento real do índice DataJud e tenta encontrar documentos
que contenham o campo 'partes'.

Uso:
    python scripts\verificar_mapping.py
"""
from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import httpx

DATAJUD_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
BASE_URL = "https://api-publica.datajud.cnj.jus.br"
TRIBUNAIS = ["tjsp", "trt2", "stj"]

async def main():
    headers = {
        "Authorization": f"APIKey {DATAJUD_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for tribunal in TRIBUNAIS:
            print(f"\n{'='*70}")
            print(f"TRIBUNAL: {tribunal.upper()}")

            # 1. Tenta o endpoint de mapeamento
            url_mapping = f"{BASE_URL}/api_publica_{tribunal}/_mapping"
            resp = await client.get(url_mapping, headers=headers)
            print(f"\n[1] Mapping (GET /_mapping): status={resp.status_code}")
            if resp.status_code == 200:
                mapping = resp.json()
                # Extrai os campos do mapping
                index_key = list(mapping.keys())[0]
                props = mapping[index_key].get("mappings", {}).get("properties", {})
                print(f"    Campos no mapping: {list(props.keys())}")
                if "partes" in props:
                    print(f"    ✓ 'partes' EXISTE no mapping!")
                    print(f"    Estrutura partes: {json.dumps(props['partes'], indent=2)[:600]}")
                else:
                    print(f"    ✗ 'partes' NÃO existe no mapping")
            else:
                print(f"    erro: {resp.text[:200]}")

            # 2. Busca documento que tenha o campo partes preenchido
            print(f"\n[2] Busca doc com 'partes' preenchido:")
            q_com_partes = {"query": {"exists": {"field": "partes"}}, "size": 1, "_source": True}
            resp2 = await client.post(
                f"{BASE_URL}/api_publica_{tribunal}/_search",
                json=q_com_partes, headers=headers
            )
            print(f"    status={resp2.status_code}")
            if resp2.status_code == 200:
                hits = resp2.json().get("hits", {}).get("hits", [])
                total = resp2.json().get("hits", {}).get("total", {})
                total_val = total.get("value", 0) if isinstance(total, dict) else total
                print(f"    docs COM partes: {total_val}")
                if hits:
                    src = hits[0].get("_source", {})
                    print(f"    numero_cnj: {src.get('numeroProcesso')}")
                    print(f"    partes: {json.dumps(src.get('partes', []), ensure_ascii=False)[:500]}")
            else:
                print(f"    erro: {resp2.text[:200]}")

            # 3. Busca com source filtering explícito pedindo partes
            print(f"\n[3] Busca com _source=['partes','numeroProcesso'] explícito:")
            q_source = {
                "query": {"match_all": {}},
                "size": 1,
                "_source": ["partes", "numeroProcesso", "partes.advogados"]
            }
            resp3 = await client.post(
                f"{BASE_URL}/api_publica_{tribunal}/_search",
                json=q_source, headers=headers
            )
            if resp3.status_code == 200:
                hits3 = resp3.json().get("hits", {}).get("hits", [])
                if hits3:
                    src3 = hits3[0].get("_source", {})
                    print(f"    campos retornados: {list(src3.keys())}")
                    print(f"    partes: {src3.get('partes', 'NÃO RETORNADO')}")

if __name__ == "__main__":
    asyncio.run(main())
