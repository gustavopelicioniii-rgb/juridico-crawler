"""
Mostra o HTML bruto de um processo específico do TJSP para diagnóstico do parser.
Útil para entender por que partes/advogados não estão sendo extraídos.

Uso:
    python scripts\debug_processo.py 1002201-27.2025.8.26.0048
    python scripts\debug_processo.py 1006882-45.2022.8.26.0048
"""
from __future__ import annotations
import asyncio, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import httpx

# Dois processos problemáticos do log (sem partes) e um que funcionou
PROCESSOS_TESTE = {
    # sem partes
    "1002201-27.2025.8.26.0048": {"codigo": "1C000703K0000", "foro": "48"},
    "1006882-45.2022.8.26.0048": {"codigo": "1C0005J6X0000", "foro": "48"},
    # com partes (para comparar)
    "0027984-37.2022.8.26.0050": {"codigo": "1E002ADRE0000", "foro": "50"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

async def main():
    numero = sys.argv[1] if len(sys.argv) > 1 else "1002201-27.2025.8.26.0048"
    info = PROCESSOS_TESTE.get(numero)
    if not info:
        print(f"Processo '{numero}' não está na lista de teste.")
        print(f"Disponíveis: {list(PROCESSOS_TESTE.keys())}")
        return

    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.codigo={info['codigo']}&processo.foro={info['foro']}"
    print(f"Buscando: {url}\n")

    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        # Inicializa sessão
        await client.get("https://esaj.tjsp.jus.br/cpopg/open.do")
        resp = await client.get(url)
        html = resp.text

    # Salva HTML completo para inspeção
    out = ROOT / "tests" / f"debug_{numero.replace('-','_').replace('.','_')}.html"
    out.write_text(html, encoding="utf-8")
    print(f"HTML salvo em: {out}")
    print(f"Tamanho: {len(html)} chars")
    print()

    # Mostra trechos relevantes
    html_lower = html.lower()

    print("=== TRECHO 'nomeParteEAdvogado' ===")
    idx = html_lower.find("nomeparteaadvogado")
    if idx > 0:
        print(html[max(0,idx-50):idx+500])
    else:
        print("(não encontrado)")
    print()

    print("=== TRECHO 'OAB' ===")
    idx = html_lower.find("oab")
    if idx > 0:
        print(html[max(0,idx-100):idx+300])
    else:
        print("(não encontrado no HTML)")
    print()

    print("=== TRECHO 'advogad' ===")
    idx = html_lower.find("advogad")
    if idx > 0:
        print(html[max(0,idx-50):idx+400])
    else:
        print("(não encontrado no HTML)")
    print()

    print("=== TRECHO 'parteAut' / 'autor' ===")
    for chave in ["parteaut", "autor", "partepas", "reu", "réu"]:
        idx = html_lower.find(chave)
        if idx > 0:
            print(f"[{chave}] encontrado em pos {idx}:")
            print(html[max(0,idx-20):idx+300])
            print()
            break

    print(f"\nAbra o arquivo HTML no navegador para inspecionar visualmente:")
    print(f"  {out}")

if __name__ == "__main__":
    asyncio.run(main())
