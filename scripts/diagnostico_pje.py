"""
Diagnóstico do PJe para OAB 361329/SP.

Verifica o que cada endpoint realmente retorna — útil para entender
por que a busca retorna 200 OK mas 0 processos.

Uso:
    python scripts\diagnostico_pje.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

OAB = "361329"
UF  = "SP"

ENDPOINTS_TESTE = [
    # TRT2 — São Paulo capital
    {
        "nome": "TRT2 API REST /advogado",
        "url": f"https://pje.trt2.jus.br/consultaprocessual/api/v1/advogado/{OAB}/processos",
        "params": {"uf": UF, "pagina": 0, "tamanhoPagina": 10},
    },
    {
        "nome": "TRT2 API REST /processo/pesquisa",
        "url": "https://pje.trt2.jus.br/consultaprocessual/api/v1/processo/pesquisa",
        "params": {"numeroOAB": OAB, "ufOAB": UF, "pagina": 0, "tamanhoPagina": 10},
    },
    # TRT15 — Campinas/SP interior
    {
        "nome": "TRT15 API REST /advogado",
        "url": f"https://pje.trt15.jus.br/consultaprocessual/api/v1/advogado/{OAB}/processos",
        "params": {"uf": UF, "pagina": 0, "tamanhoPagina": 10},
    },
    # TST — Tribunal Superior do Trabalho
    {
        "nome": "TST API REST pje.tst",
        "url": f"https://pje.tst.jus.br/consultaprocessual/api/v1/advogado/{OAB}/processos",
        "params": {"uf": UF, "pagina": 0, "tamanhoPagina": 10},
    },
    {
        "nome": "TST consultaprocessual REST (alternativo)",
        "url": f"https://consultaprocessual.tst.jus.br/consultaProcessual/rest/pje/advogado/{OAB}",
        "params": {"uf": UF, "pagina": 1, "tamanhoPagina": 10},
    },
    # TRF3 — Justiça Federal SP/MS
    {
        "nome": "TRF3 eProc consulta pública",
        "url": "https://eproc.trf3.jus.br/eprocV2/controlador_externo.php",
        "params": {"acao": "advogado_processos", "num_oab": OAB, "uf_oab": UF, "evento": "listar"},
    },
    {
        "nome": "TRF3 PJe API /advogado",
        "url": f"https://pje.trf3.jus.br/consultaprocessual/api/v1/advogado/{OAB}/processos",
        "params": {"uf": UF, "pagina": 0, "tamanhoPagina": 10},
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


async def testar_endpoint(client: httpx.AsyncClient, ep: dict) -> None:
    nome   = ep["nome"]
    url    = ep["url"]
    params = ep.get("params", {})

    print(f"\n{'─'*60}")
    print(f"  {nome}")
    print(f"  URL: {url}")
    print(f"  Params: {params}")

    try:
        r = await client.get(url, params=params, timeout=15)
        print(f"  Status: {r.status_code}")
        ct = r.headers.get("content-type", "")
        print(f"  Content-Type: {ct}")

        if "json" in ct:
            try:
                data = r.json()
                # Mostra as chaves de topo e a contagem de itens
                if isinstance(data, list):
                    print(f"  Resposta: lista com {len(data)} itens")
                    if data:
                        print(f"  Amostra[0] chaves: {list(data[0].keys()) if isinstance(data[0], dict) else data[0]}")
                elif isinstance(data, dict):
                    print(f"  Resposta (dict) chaves: {list(data.keys())}")
                    # Procura o campo que contém a lista de processos
                    for k, v in data.items():
                        if isinstance(v, list):
                            print(f"    '{k}' → lista com {len(v)} item(ns)")
                            if v and isinstance(v[0], dict):
                                print(f"      amostra[0] chaves: {list(v[0].keys())}")
                        elif isinstance(v, (int, float, str, bool)):
                            print(f"    '{k}' = {v!r}")
                # Salva resposta completa para análise
                out = ROOT / "tests" / f"diagnostico_pje_{nome.replace(' ', '_').replace('/', '_')}.json"
                out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"  ✓ Resposta completa salva: {out.name}")
            except Exception as ex:
                print(f"  Erro ao parsear JSON: {ex}")
                print(f"  Texto (primeiros 500): {r.text[:500]!r}")
        else:
            # HTML / outro
            txt = r.text
            # Procura números de processo no HTML
            import re
            numeros = re.findall(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}", txt)
            print(f"  Números CNJ encontrados no HTML: {len(numeros)}")
            if numeros:
                print(f"  Exemplos: {numeros[:3]}")
            print(f"  HTML (primeiros 300): {txt[:300]!r}")

    except httpx.TimeoutException:
        print(f"  TIMEOUT após 15s")
    except httpx.ConnectError as e:
        print(f"  CONNECT ERROR: {e}")
    except Exception as e:
        print(f"  ERRO: {type(e).__name__}: {e}")


async def main() -> None:
    print(f"Diagnóstico PJe — OAB {OAB}/{UF}")
    print("=" * 60)

    (ROOT / "tests").mkdir(exist_ok=True)

    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for ep in ENDPOINTS_TESTE:
            await testar_endpoint(client, ep)

    print(f"\n{'='*60}")
    print("Diagnóstico concluído.")
    print("Veja os arquivos diagnostico_pje_*.json em tests/ para análise completa.")


if __name__ == "__main__":
    asyncio.run(main())
