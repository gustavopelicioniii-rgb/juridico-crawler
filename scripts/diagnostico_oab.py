"""
Diagnóstico rápido: testa a query OAB no DataJud e mostra o raw da primeira resposta.
Útil para debugar quando o resultado vem vazio.

Uso:
    python scripts/diagnostico_oab.py
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

NUMERO_OAB = "361329"
UF_OAB = "SP"

# Tribunais menores primeiro; TJSP por último (índice gigante)
TRIBUNAIS_TESTE = ["trt2", "trt15", "trf3", "stj", "tjsp"]


def queries_para_testar(numero_oab: str, uf_oab: str) -> list[tuple[str, dict]]:
    """
    Retorna múltiplas variações de query para descobrir qual o DataJud aceita.
    O mapeamento de 'partes.advogados' varia por índice (nested vs object).
    """
    num_limpo = numero_oab.lstrip("0") or numero_oab
    variantes = list({numero_oab, num_limpo, num_limpo.zfill(7)})

    # ── Estratégia A: duplo nested (partes nested + advogados nested) ──────────
    # Funciona se advogados for mapeado como nested no ES
    q_duplo_nested = {
        "query": {
            "nested": {
                "path": "partes",
                "query": {
                    "nested": {
                        "path": "partes.advogados",
                        "query": {
                            "bool": {
                                "must": [
                                    {"bool": {"should": [
                                        {"match": {"partes.advogados.numeroOAB": v}}
                                        for v in variantes
                                    ], "minimum_should_match": 1}},
                                    {"match": {"partes.advogados.ufOAB": uf_oab.upper()}},
                                ]
                            }
                        },
                    }
                },
            }
        },
        "size": 3, "_source": True,
    }

    # ── Estratégia B: nested só em partes, advogados como objeto comum ────────
    # Funciona se advogados for object (não nested) dentro de partes nested
    q_nested_simples = {
        "query": {
            "nested": {
                "path": "partes",
                "query": {
                    "bool": {
                        "must": [
                            {"bool": {"should": [
                                {"match": {"partes.advogados.numeroOAB": v}}
                                for v in variantes
                            ], "minimum_should_match": 1}},
                            {"match": {"partes.advogados.ufOAB": uf_oab.upper()}},
                        ]
                    }
                },
            }
        },
        "size": 3, "_source": True,
    }

    # ── Estratégia C: sem nested, campos no topo do documento ────────────────
    # Alguns índices menores do DataJud não usam nested
    q_sem_nested = {
        "query": {
            "bool": {
                "must": [
                    {"bool": {"should": [
                        {"match": {"partes.advogados.numeroOAB": v}}
                        for v in variantes
                    ], "minimum_should_match": 1}},
                    {"match": {"partes.advogados.ufOAB": uf_oab.upper()}},
                ]
            }
        },
        "size": 3, "_source": True,
    }

    return [
        ("A: duplo_nested", q_duplo_nested),
        ("B: nested_simples", q_nested_simples),
        ("C: sem_nested", q_sem_nested),
    ]


async def main():
    queries = queries_para_testar(NUMERO_OAB, UF_OAB)
    headers = {
        "Authorization": f"APIKey {DATAJUD_KEY}",
        "Content-Type": "application/json",
    }

    print(f"Testando OAB {NUMERO_OAB}/{UF_OAB}")
    print(f"Tribunais: {TRIBUNAIS_TESTE}")
    print(f"Estratégias de query: {[nome for nome, _ in queries]}")
    print("=" * 70)

    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        for tribunal in TRIBUNAIS_TESTE:
            url = f"{BASE_URL}/api_publica_{tribunal}/_search"
            print(f"\n[{tribunal.upper()}]")

            for nome_q, query in queries:
                try:
                    resp = await client.post(url, json=query, headers=headers)
                    data = resp.json()
                    total = data.get("hits", {}).get("total", {})
                    hits = data.get("hits", {}).get("hits", [])
                    total_val = total.get("value", 0) if isinstance(total, dict) else total

                    status_icon = "✓" if resp.status_code == 200 else "✗"
                    print(f"  {status_icon} {nome_q:20} status={resp.status_code}  total={total_val}  hits={len(hits)}")

                    if hits:
                        primeiro = hits[0].get("_source", {})
                        print(f"    → campos: {list(primeiro.keys())}")
                        print(f"    → numero_cnj:  {primeiro.get('numeroProcesso', '—')}")
                        print(f"    → valorCausa:  {primeiro.get('valorCausa', '—')}")
                        print(f"    → nivelSigilo: {primeiro.get('nivelSigilo', 0)}")
                        partes_raw = primeiro.get("partes", [])
                        print(f"    → partes count: {len(partes_raw)}")
                        if partes_raw:
                            p0 = partes_raw[0]
                            print(f"    → 1a parte: {json.dumps(p0, ensure_ascii=False)[:300]}")
                        break  # Achou com essa estratégia, para de testar as outras

                    if resp.status_code == 400:
                        erro = data.get("error", {})
                        print(f"    → erro: {str(erro)[:150]}")

                except Exception as e:
                    print(f"  ✗ {nome_q:20} ERRO: {type(e).__name__}: {str(e)[:80]}")

    print("\n" + "=" * 70)
    print("Estratégia que retornou hits = a correta para esse tribunal.")


if __name__ == "__main__":
    asyncio.run(main())
