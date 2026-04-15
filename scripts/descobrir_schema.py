"""
Descoberta de schema: busca 1 documento qualquer do DataJud e imprime
TODOS os campos e a estrutura aninhada completa. Objetivo: descobrir
o nome real dos campos de OAB no índice atual.

Uso:
    python scripts\descobrir_schema.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

DATAJUD_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw=="
BASE_URL = "https://api-publica.datajud.cnj.jus.br"

# Tribunais menores para resposta rápida
TRIBUNAIS = ["stj", "trt2", "tjsp"]


def achatar_chaves(obj, prefix=""):
    """Retorna todas as chaves aninhadas no formato 'a.b.c'."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            novo = f"{prefix}.{k}" if prefix else k
            yield novo
            yield from achatar_chaves(v, novo)
    elif isinstance(obj, list) and obj:
        # Para listas, pega o primeiro item como amostra
        yield from achatar_chaves(obj[0], prefix + "[]")


async def main():
    headers = {
        "Authorization": f"APIKey {DATAJUD_KEY}",
        "Content-Type": "application/json",
    }
    # Query totalmente vazia — pega qualquer documento do índice
    query_generica = {
        "query": {"match_all": {}},
        "size": 1,
    }

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for tribunal in TRIBUNAIS:
            print(f"\n{'='*70}")
            print(f"TRIBUNAL: {tribunal.upper()}")
            print("=" * 70)

            url = f"{BASE_URL}/api_publica_{tribunal}/_search"
            try:
                resp = await client.post(url, json=query_generica, headers=headers)
                print(f"status: {resp.status_code}")
                if resp.status_code != 200:
                    print(f"erro: {resp.text[:300]}")
                    continue

                data = resp.json()
                hits = data.get("hits", {}).get("hits", [])
                total = data.get("hits", {}).get("total", {})
                print(f"total no índice: {total.get('value', total) if isinstance(total, dict) else total}")

                if not hits:
                    print("(nenhum documento)")
                    continue

                source = hits[0].get("_source", {})
                print(f"\n── CAMPOS TOP-LEVEL ──")
                for k in source.keys():
                    tipo = type(source[k]).__name__
                    valor = str(source[k])[:80]
                    print(f"  {k:25} ({tipo:10}) = {valor}")

                print(f"\n── TODAS AS CHAVES ANINHADAS (caminhos reais) ──")
                chaves = sorted(set(achatar_chaves(source)))
                for c in chaves:
                    print(f"  {c}")

                # Destaque para partes e advogados
                print(f"\n── DESTAQUE: procurando OAB ──")
                json_str = json.dumps(source, ensure_ascii=False).lower()
                for chave in ["oab", "numerooab", "inscricao", "advogad"]:
                    if chave in json_str:
                        # Encontra e imprime trechos relevantes
                        idx = json_str.find(chave)
                        print(f"  '{chave}' encontrado em pos {idx}")
                        trecho = json.dumps(source, ensure_ascii=False)[max(0, idx-30):idx+200]
                        print(f"    ...{trecho}...")
                        break
                else:
                    print("  nenhuma referência a OAB/advogado encontrada no 1º doc (pode estar vazio)")

                # Imprime a estrutura de "partes" ou equivalente se existir
                for campo_teste in ["partes", "polo", "dadosBasicos"]:
                    if campo_teste in source:
                        print(f"\n── {campo_teste.upper()} (primeiros 500 chars) ──")
                        print(json.dumps(source[campo_teste], ensure_ascii=False, indent=2)[:500])

            except Exception as e:
                print(f"ERRO: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
