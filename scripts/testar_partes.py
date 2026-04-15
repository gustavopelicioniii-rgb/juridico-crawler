"""
Testa extração de partes diretamente no DataJud — sem a API rodando.

Uso:
    python scripts/testar_partes.py 0002371-37.2024.8.26.0050 tjsp
    python scripts/testar_partes.py 0001234-56.2024.5.02.0001 trt2
"""

import asyncio
import json
import sys
from pathlib import Path

# Adiciona raiz do projeto ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

# Lê do .env via settings; fallback para a chave pública padrão do CNJ
try:
    from src.config import settings as _cfg
    DATAJUD_KEY = _cfg.datajud_api_key
    DATAJUD_BASE = _cfg.datajud_base_url
except Exception:
    DATAJUD_KEY = "cDZHYzlZa0JadVREZDJCendQbXY6SnJSSmdzMHFhUXFCaVhpSHJlUjNmQQ=="
    DATAJUD_BASE = "https://api-publica.datajud.cnj.jus.br"

TRIBUNAL_SUFIXO = {
    "tjsp": "tjsp", "trt2": "trt2-sp", "trf3": "trf3", "stj": "stj",
    "tjrj": "tjrj", "tjmg": "tjmg", "tst": "tst",
}


async def testar(numero_cnj: str, tribunal: str) -> None:
    sufixo = TRIBUNAL_SUFIXO.get(tribunal.lower(), tribunal.lower())
    url = f"{DATAJUD_BASE}/api_publica_{sufixo}/_search"

    payload = {
        "query": {"match": {"numeroProcesso": numero_cnj}},
        "size": 1,
    }

    print(f"\n🔍 Consultando DataJud — {tribunal.upper()}")
    print(f"   URL: {url}")
    print(f"   CNJ: {numero_cnj}\n")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"APIKey {DATAJUD_KEY}",
                "Content-Type": "application/json",
            },
        )
        r.raise_for_status()
        data = r.json()

    hits = data.get("hits", {}).get("hits", [])
    if not hits:
        print("❌ Processo NÃO encontrado no DataJud.")
        print(f"   Total hits: {data.get('hits', {}).get('total', {})}")
        return

    source = hits[0]["_source"]

    print("✅ Processo encontrado!\n")
    print(f"📋 Campos disponíveis ({len(source)} campos):")
    print(f"   {list(source.keys())}\n")

    partes_raw = source.get("partes", [])
    print(f"👥 Campo 'partes': {len(partes_raw)} registro(s)")

    if partes_raw:
        print("\n   Estrutura da primeira parte:")
        print(json.dumps(partes_raw[0], indent=4, ensure_ascii=False))
        if len(partes_raw) > 1:
            print(f"\n   ... e mais {len(partes_raw) - 1} parte(s)\n")
    else:
        print("   ⚠  Campo 'partes' está VAZIO ou não existe!\n")
        # Checar campos alternativos
        for campo in ("parteAtiva", "partePassiva", "polo_ativo", "polo_passivo"):
            if source.get(campo):
                print(f"   ℹ  Campo alternativo '{campo}': {source[campo]}")

    # Testar o parser determinístico
    try:
        from src.parsers.ai_parser import extrair_partes_do_datajud
        partes = extrair_partes_do_datajud(source)
        print(f"\n🧩 Parser determinístico extraiu {len(partes)} parte(s):")
        for p in partes:
            oab_str = f" [OAB {p.oab}]" if p.oab else ""
            print(f"   [{p.polo or '?'}] {p.tipo_parte}: {p.nome}{oab_str}")
    except ImportError:
        print("\n⚠  Parser não disponível (rode da raiz do projeto)")

    print(f"\n📄 JSON completo (primeiros 3000 chars):")
    print(json.dumps(source, indent=2, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python scripts/testar_partes.py <numero_cnj> <tribunal>")
        print("Ex:  python scripts/testar_partes.py 0002371-37.2024.8.26.0050 tjsp")
        sys.exit(1)

    asyncio.run(testar(sys.argv[1], sys.argv[2]))
