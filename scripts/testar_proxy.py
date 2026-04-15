"""
Testa o proxy residencial configurado no .env.

Verifica:
  1. IP de saída via proxy (ipinfo.io) — confirma que o proxy funciona e qual país/cidade
  2. IP de saída SEM proxy — para comparação
  3. Acesso a TJs que bloqueiam IPs não-brasileiros — compara com e sem proxy

Uso:
    python scripts/testar_proxy.py
"""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Carrega .env via pydantic-settings (mesmo mecanismo usado pelos crawlers)
from src.config import settings  # noqa: E402
from src.crawlers.base import ProxyPool  # noqa: E402

import httpx  # noqa: E402


def montar_proxy_url() -> str | None:
    pool = ProxyPool.from_env()
    return pool.next()  # None se PROXY_LIST vazio


async def testar(label: str, url: str, proxy: str | None = None):
    kwargs: dict = dict(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
    )
    if proxy:
        kwargs["proxy"] = proxy
        # Proxies residenciais fazem interceptação SSL — desabilitar verificação
        kwargs["verify"] = False

    try:
        async with httpx.AsyncClient(**kwargs) as client:
            r = await client.get(url)
            body = r.text[:300].strip()
            print(f"  ✓ [{label}] status={r.status_code}  body={body}")
            return r
    except Exception as e:
        print(f"  ✗ [{label}] ERRO: {type(e).__name__}: {e!r}")
        return None


async def main():
    proxy = montar_proxy_url()

    if not proxy:
        print("❌ PROXY_LIST não configurado no .env")
        print("   Adicione: PROXY_LIST=http://user:pass@host:porta")
        print()
        print("   Exemplo ProxyScrape:")
        print("   PROXY_LIST=http://{api_key}-country-br:@residential.proxyscrape.com:6060")
        sys.exit(1)

    # Esconde credenciais no log (mostra só host:porta)
    proxy_display = proxy.split("@")[-1] if "@" in proxy else proxy
    pool = ProxyPool.from_env()
    print(f"Proxy configurado: {proxy_display}  ({len(pool.proxies)} IP(s) no pool)")
    print()

    # ── 1. IP de saída via proxy ──────────────────────────────────────────
    print("[1] IP de saída via proxy (ipinfo.io):")
    r = await testar("ipinfo.io (com proxy)", "https://ipinfo.io/json", proxy=proxy)
    proxy_ok = r is not None and r.status_code == 200
    if proxy_ok:
        import json
        try:
            info = json.loads(r.text)
            print(f"     → IP: {info.get('ip')}  País: {info.get('country')}  Cidade: {info.get('city')}")
            if info.get("country") != "BR":
                print(f"     ⚠️  IP não é brasileiro — use -country-br no endpoint para garantir IP do Brasil")
        except Exception:
            pass

    # ── 2. IP real (sem proxy) ────────────────────────────────────────────
    print()
    print("[2] IP de saída SEM proxy (seu IP real):")
    r2 = await testar("ipinfo.io (sem proxy)", "https://ipinfo.io/json")
    if r2 and r2.status_code == 200:
        import json
        try:
            info2 = json.loads(r2.text)
            print(f"     → IP: {info2.get('ip')}  País: {info2.get('country')}  Cidade: {info2.get('city')}")
        except Exception:
            pass

    # ── 3. TJs — usando as URLs REAIS do eSAJ (mesmo path do crawler) ────
    print()
    print("[3] TJs eSAJ — URLs reais usadas pelo crawler (cpopg/open.do):")

    tjs = [
        ("TJMS", "https://esaj.tjms.jus.br/cpopg/open.do"),       # referência (sempre funciona)
        ("TJMG", "https://sistemas.tjmg.jus.br/cpopg/open.do"),   # DNS falha em alguns ISPs
        ("TJRJ", "https://esaj4.tjrj.jus.br/cpopg/open.do"),
        ("TJPR", "https://esaj.tjpr.jus.br/cpopg/open.do"),
        ("TJSC", "https://esaj.tjsc.jus.br/cpopg/open.do"),
        ("TJRS", "https://esaj.tjrs.jus.br/cpopg/open.do"),
        ("TJGO", "https://esaj.tjgo.jus.br/cpopg/open.do"),
        ("TJMT", "https://esaj.tjmt.jus.br/cpopg/open.do"),
        ("TJPA", "https://esaj.tjpa.jus.br/cpopg/open.do"),
        ("TJES", "https://esaj.tjes.jus.br/cpopg/open.do"),
    ]

    resultados_tj = []
    for nome, url in tjs:
        print(f"  {nome}:")
        print(f"    SEM proxy → ", end="", flush=True)
        r_sem = await testar(f"{nome} sem proxy", url)
        print(f"    COM proxy → ", end="", flush=True)
        r_com = await testar(f"{nome} com proxy", url, proxy=proxy)
        sem_ok = r_sem is not None and r_sem.status_code < 400
        com_ok = r_com is not None and r_com.status_code < 400
        resultados_tj.append((nome, sem_ok, com_ok))
        print()

    # ── Resumo ─────────────────────────────────────────────────────────
    print("=" * 60)
    if proxy_ok:
        print("✓ Proxy conectando OK")
        desbloqueados = [n for n, _, com in resultados_tj if com]
        bloqueados    = [n for n, _, com in resultados_tj if not com]
        if desbloqueados:
            print(f"✓ TJs acessíveis via proxy: {', '.join(desbloqueados)}")
        if bloqueados:
            print(f"⚠  TJs ainda bloqueados via proxy: {', '.join(bloqueados)}")
        print()
        print("Próximo passo: python scripts/testar_oab_361329.py")
    else:
        print("✗ Proxy com problema — verifique credenciais no dashboard ProxyScrape")
        print()
        print("Possíveis causas:")
        print("  - API key incorreta")
        print("  - Créditos esgotados")
        print("  - Endpoint ou porta errados (verifique no dashboard)")


if __name__ == "__main__":
    asyncio.run(main())
