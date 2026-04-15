"""
Mineração completa de processos para OAB 361329/SP.

ESTRATÉGIA CORRETA (DataJud público não retorna partes/advogados desde 2024):
  1. TJSP eSAJ   → busca por OAB no portal tjsp.jus.br (cbPesquisa=NUMOAB)
  2. PJe         → API REST /advogado/{oab}/processos + fallback HTML
  3. eSAJ outros → TJs de outros estados com sistema eSAJ
  4. STJ         → portal de consulta processual
  5. DataJud     → só complementa metadados (valor, classe, assuntos)
                   quando já temos o número CNJ — NÃO para buscar por OAB

Uso:
    python scripts\testar_oab_361329.py

    # Só TJSP (mais rápido para primeiro teste):
    set OAB_SOMENTE_TJSP=1
    python scripts\testar_oab_361329.py

Saída:
    tests\resultado_oab_361329.json        — todos os processos
    tests\resultado_oab_361329_segredo.json — só os em segredo de justiça
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.crawlers.tjsp import TJSPCrawler                          # noqa: E402
from src.crawlers.pje import PJeCrawler, PJE_URLS                  # noqa: E402
from src.crawlers.esaj_generico import ESajMultiCrawler            # noqa: E402
from src.crawlers.datajud import DataJudCrawler, TRIBUNAL_ENDPOINT  # noqa: E402
from src.crawlers.stj import STJCrawler                            # noqa: E402
from src.crawlers.tst import TSTCrawler                            # noqa: E402
from src.crawlers.trf import TRFCrawler                            # noqa: E402
from src.crawlers.base import ProxyPool                            # noqa: E402
from src.parsers.estruturas import ProcessoCompleto                # noqa: E402
from src.database.connection import AsyncSessionLocal, create_tables  # noqa: E402
from src.services.processo_service import ProcessoService          # noqa: E402

SEM_PROXY = ProxyPool([])   # todos os crawlers usam conexão direta

NUMERO_OAB = "361329"
UF_OAB = "SP"

# Tribunais PJe relevantes para OAB/SP — apenas TRTs trabalhistas
# TRF3 e TST testados nos steps dedicados (4 e 3)
TRIBUNAIS_PJE_SP = ["trt2", "trt15", "trt9"]

# Tribunais para busca no DataJud — todos EXCETO os já cobertos por scrapers dedicados
# (TJSP → scraper próprio, TRTs → PJe, TRF3 → TRFCrawler, TST → TSTCrawler)
TRIBUNAIS_DATAJUD = [
    t for t in TRIBUNAL_ENDPOINT
    if t not in {"tjsp", "trt2", "trt15", "trt9", "trf3", "tst", "stj"}
]


def json_default(obj):
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def processo_para_dict(p: ProcessoCompleto) -> dict:
    d = asdict(p)
    d.pop("dados_brutos", None)
    return d


def resumir(p: ProcessoCompleto) -> str:
    autores = [pt.nome for pt in p.partes if pt.polo == "ATIVO" and pt.tipo_parte != "ADVOGADO"][:2]
    reus    = [pt.nome for pt in p.partes if pt.polo == "PASSIVO" and pt.tipo_parte != "ADVOGADO"][:2]
    # Mostra nome do advogado; inclui OAB entre parênteses se disponível
    advs_parts = [pt for pt in p.partes if pt.tipo_parte == "ADVOGADO"][:3]
    advs = [
        f"{pt.nome} ({pt.oab})" if pt.oab else pt.nome
        for pt in advs_parts
    ]
    flag    = "🔒" if p.segredo_justica else "  "
    valor   = f"R$ {p.valor_causa:,.2f}" if p.valor_causa else "—"
    n_partes = len([pt for pt in p.partes if pt.tipo_parte != "ADVOGADO"])
    n_advs   = len(advs_parts)
    return (
        f"{flag} [{p.tribunal:6}] {p.numero_cnj or '—'}\n"
        f"       autor={autores or '—'}  réu={reus or '—'}\n"
        f"       valor={valor}  partes={n_partes}  advogados={n_advs}\n"
        f"       advs={advs}"
        + (f"\n       obs={p.observacoes}" if getattr(p, "observacoes", None) else "")
    )


async def main() -> int:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    somente_tjsp = os.getenv("OAB_SOMENTE_TJSP", "").strip() == "1"

    print(f"→ Minerando OAB {NUMERO_OAB}/{UF_OAB}")
    print(f"→ Modo: {'apenas TJSP' if somente_tjsp else 'todos os tribunais'}")
    print()

    resultados_por_sistema: dict[str, list[ProcessoCompleto]] = {}

    # ── 1. TJSP eSAJ ────────────────────────────────────────────────────────
    print("  [1/7] TJSP eSAJ...", flush=True)
    try:
        async with TJSPCrawler(requests_per_minute=60, proxy_pool=SEM_PROXY) as c:
            lista = await c.buscar_por_oab(
                numero_oab=NUMERO_OAB,
                uf_oab=UF_OAB,
                paginas=20,   # 20 pág × ~25 proc = até 500 processos
            )
        resultados_por_sistema["tjsp"] = lista
        print(f"         → {len(lista)} processo(s)")
    except Exception as e:
        print(f"         → ERRO: {type(e).__name__}: {e}")
        resultados_por_sistema["tjsp"] = []

    if somente_tjsp:
        print("  (pulando PJe/TST/TRF/eSAJ/STJ — modo TJSP only)")
    else:
        # ── 2. PJe (TRTs trabalhistas) ──────────────────────────────────────
        print("  [2/7] PJe — TRTs trabalhistas (TRT2, TRT15, TRT9)...", flush=True)
        # TST e TRF3 são testados nos steps dedicados (3 e 4)
        try:
            alvos_pje = [t for t in TRIBUNAIS_PJE_SP if t in PJE_URLS]
            async with PJeCrawler(requests_per_minute=30, proxy_pool=SEM_PROXY) as c:
                lista = await c.buscar_por_oab(
                    numero_oab=NUMERO_OAB,
                    uf_oab=UF_OAB,
                    tribunais=alvos_pje,
                    tamanho=100,
                )
            resultados_por_sistema["pje"] = lista
            print(f"         → {len(lista)} processo(s)")
        except Exception as e:
            print(f"         → ERRO: {type(e).__name__}: {e}")
            resultados_por_sistema["pje"] = []

        # ── 3. TST ──────────────────────────────────────────────────────────
        print("  [3/7] TST — Tribunal Superior do Trabalho...", flush=True)
        try:
            async with TSTCrawler(requests_per_minute=30, proxy_pool=SEM_PROXY) as c:
                lista = await c.buscar_por_oab(
                    numero_oab=NUMERO_OAB,
                    uf_oab=UF_OAB,
                    paginas=10,
                    tamanho_pagina=20,
                )
            resultados_por_sistema["tst"] = lista
            print(f"         → {len(lista)} processo(s)")
        except Exception as e:
            print(f"         → ERRO: {type(e).__name__}: {e}")
            resultados_por_sistema["tst"] = []

        # ── 4. TRF3 (Justiça Federal SP/MS) ────────────────────────────────
        print("  [4/7] TRF3 — Justiça Federal SP/MS...", flush=True)
        try:
            async with TRFCrawler(requests_per_minute=20, proxy_pool=SEM_PROXY) as c:
                lista = await c.buscar_por_oab(
                    numero_oab=NUMERO_OAB,
                    uf_oab=UF_OAB,
                    tribunais=["trf3"],
                )
            resultados_por_sistema["trf3"] = lista
            print(f"         → {len(lista)} processo(s)")
        except Exception as e:
            print(f"         → ERRO: {type(e).__name__}: {e}")
            resultados_por_sistema["trf3"] = []

        # ── 5. eSAJ outros TJs (apenas TJMS — único com DNS público) ────────
        print("  [5/7] eSAJ — TJMS (único acessível via DNS público)...", flush=True)
        try:
            async with ESajMultiCrawler(proxy_pool=SEM_PROXY) as c:
                lista = await c.buscar_por_oab(
                    numero_oab=NUMERO_OAB,
                    uf_oab=UF_OAB,
                    tribunais=["tjms"],   # outros TJs não têm DNS público
                    paginas=3,
                )
            resultados_por_sistema["esaj_tjms"] = lista
            print(f"         → {len(lista)} processo(s)")
        except Exception as e:
            print(f"         → ERRO: {type(e).__name__}: {e}")
            resultados_por_sistema["esaj_tjms"] = []

        # ── 6. DataJud CNJ — todos os outros tribunais ───────────────────────
        # Os domínios esaj.*.jus.br da maioria dos TJs estaduais não estão em
        # DNS público (apenas na Rede JUS interna). O DataJud CNJ indexa
        # processos de TODOS os tribunais e é acessível sem proxy.
        print(f"  [6/7] DataJud CNJ — {len(TRIBUNAIS_DATAJUD)} tribunal(is)...", flush=True)
        try:
            async with DataJudCrawler(requests_per_minute=60, proxy_pool=SEM_PROXY) as c:
                lista = await c.buscar_por_oab(
                    numero_oab=NUMERO_OAB,
                    uf_oab=UF_OAB,
                    tribunais=TRIBUNAIS_DATAJUD,
                    tamanho_por_tribunal=100,
                    usar_ai_parser=False,
                    max_concorrentes=20,
                )
            resultados_por_sistema["datajud"] = lista
            # Agrupa por tribunal para diagnóstico
            por_trib_dj: dict[str, int] = {}
            for p in lista:
                por_trib_dj[p.tribunal] = por_trib_dj.get(p.tribunal, 0) + 1
            print(f"         → {len(lista)} processo(s) em {len(por_trib_dj)} tribunal(is)")
            if por_trib_dj:
                for t, n in sorted(por_trib_dj.items(), key=lambda kv: -kv[1])[:10]:
                    print(f"           {t}: {n}")
        except Exception as e:
            print(f"         → ERRO: {type(e).__name__}: {e}")
            resultados_por_sistema["datajud"] = []

        # ── 7. STJ ──────────────────────────────────────────────────────────
        print("  [7/7] STJ...", flush=True)
        try:
            async with STJCrawler(requests_per_minute=20, proxy_pool=SEM_PROXY) as c:
                lista = await c.buscar_por_oab(
                    numero_oab=NUMERO_OAB,
                    uf_oab=UF_OAB,
                    paginas=5,
                )
            resultados_por_sistema["stj"] = lista
            print(f"         → {len(lista)} processo(s)")
        except Exception as e:
            print(f"         → ERRO: {type(e).__name__}: {e}")
            resultados_por_sistema["stj"] = []

    # ── Dedup por número CNJ ────────────────────────────────────────────────
    unicos: dict[str, ProcessoCompleto] = {}
    for sistema, lista in resultados_por_sistema.items():
        for p in lista:
            if not p.numero_cnj:
                continue
            atual = unicos.get(p.numero_cnj)
            if atual is None or len(p.partes) > len(atual.partes):
                unicos[p.numero_cnj] = p

    processos = sorted(
        unicos.values(),
        key=lambda x: x.data_distribuicao or date.min,
        reverse=True,
    )

    # ── Estatísticas ────────────────────────────────────────────────────────
    total      = len(processos)
    com_partes = sum(1 for p in processos if any(pt.tipo_parte != "ADVOGADO" for pt in p.partes))
    com_advs   = sum(1 for p in processos if any(pt.tipo_parte == "ADVOGADO" for pt in p.partes))
    com_valor  = sum(1 for p in processos if p.valor_causa is not None)
    em_segredo = [p for p in processos if p.segredo_justica]
    por_trib: dict[str, int] = {}
    for p in processos:
        t = p.tribunal or "?"
        por_trib[t] = por_trib.get(t, 0) + 1

    pct = lambda n: f"{100*n//max(total,1)}%"

    print()
    print("=" * 70)
    print(f"RESULTADO — OAB {NUMERO_OAB}/{UF_OAB}")
    print("=" * 70)
    print(f"Total processos únicos:    {total}")
    print(f"  com partes extraídas:    {com_partes} ({pct(com_partes)})")
    print(f"  com advogados extraídos: {com_advs} ({pct(com_advs)})")
    print(f"  com valor da causa:      {com_valor} ({pct(com_valor)})")
    print(f"  em segredo de justiça:   {len(em_segredo)}")
    print(f"\nPor sistema:")
    for s, n in resultados_por_sistema.items():
        print(f"  {s:<15} {len(n):>5}")
    print(f"\nPor tribunal:")
    for t, n in sorted(por_trib.items(), key=lambda kv: -kv[1]):
        print(f"  {t:<12} {n:>5}")

    print(f"\nAmostra (primeiros 10):")
    for p in processos[:10]:
        print(f"  {resumir(p)}")

    if em_segredo:
        print(f"\nEm segredo ({len(em_segredo)}):")
        for p in em_segredo[:5]:
            print(f"  🔒 {p.numero_cnj} [{p.tribunal}]")
            print(f"     {p.observacoes}")

    # ── Salva JSONs ─────────────────────────────────────────────────────────
    out_dir = ROOT / "tests"
    out_dir.mkdir(exist_ok=True)
    out_completo = out_dir / "resultado_oab_361329.json"
    out_segredo  = out_dir / "resultado_oab_361329_segredo.json"

    with open(out_completo, "w", encoding="utf-8") as f:
        json.dump([processo_para_dict(p) for p in processos], f,
                  ensure_ascii=False, indent=2, default=json_default)
    with open(out_segredo, "w", encoding="utf-8") as f:
        json.dump([processo_para_dict(p) for p in em_segredo], f,
                  ensure_ascii=False, indent=2, default=json_default)

    print(f"\n✓ Completo:         {out_completo}")
    print(f"✓ Segredo justiça:  {out_segredo}")

    # ── Salva em PostgreSQL (Bloco 1: Persistência) ──────────────────────────
    print()
    print("=" * 70)
    print("PERSISTÊNCIA EM POSTGRESQL")
    print("=" * 70)
    try:
        # Cria tabelas se não existirem (dev only)
        await create_tables()

        async with AsyncSessionLocal() as db:
            service = ProcessoService(db)
            stats = await service.salvar_processos(
                processos,
                criar_monitoramento=False,  # Vai ser preenchido no Bloco 2 (scheduler)
            )

        print(f"✓ Banco de dados:")
        print(f"  Total processados:       {stats['total']}")
        print(f"  Novos:                   {stats['novos']}")
        print(f"  Atualizados:             {stats['atualizados']}")
        print(f"  Movimentações novas:     {stats['movimentacoes_novas_total']}")
        if stats['erros']:
            print(f"  ⚠  Erros:                {len(stats['erros'])}")
            for e in stats['erros'][:3]:
                print(f"      - {e}")
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Erro ao salvar em PostgreSQL: {type(e).__name__}: {e}")
        print(f"✗ Erro ao salvar em PostgreSQL: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
