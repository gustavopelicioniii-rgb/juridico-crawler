"""
Teste de 10 buscas com OABs diferentes para validar o sistema.
Usa DataJud (API pública CNJ) como motor principal.
"""
import asyncio
import sys
import os
import time

# Forcar UTF-8 no terminal Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.getcwd())

from src.crawlers.datajud import DataJudCrawler

# 10 OABs variadas de diferentes UFs para testar cobertura real
OABS_TESTE = [
    ("361329", "SP"),   # OAB SP - caso original do projeto
    ("100001", "SP"),   # OAB SP
    ("50000",  "RJ"),   # OAB RJ
    ("123456", "MG"),   # OAB MG
    ("80000",  "RS"),   # OAB RS
    ("45000",  "BA"),   # OAB BA
    ("30000",  "PR"),   # OAB PR
    ("20000",  "PE"),   # OAB PE
    ("15000",  "GO"),   # OAB GO
    ("10000",  "SC"),   # OAB SC
]

async def testar_oab(crawler: DataJudCrawler, oab: str, uf: str, idx: int) -> dict:
    inicio = time.time()
    print(f"\n[{idx:02d}/10] Buscando OAB {oab}/{uf}...", end=" ", flush=True)
    try:
        processos = await crawler.buscar_por_oab(
            numero_oab=oab,
            uf_oab=uf,
            tamanho_por_tribunal=20,       # max 20 por tribunal neste teste
            paginar_ate_exaustao=False,     # só 1 página por tribunal
            max_concorrentes=30,
        )
        duracao = time.time() - inicio

        # Análise rápida dos resultados
        com_partes = sum(1 for p in processos if p.partes)
        com_movs   = sum(1 for p in processos if p.movimentacoes)
        segredos   = sum(1 for p in processos if p.segredo_justica)
        tribunais  = len(set(p.tribunal for p in processos))

        print(f"OK {len(processos)} processo(s) | {duracao:.1f}s")

        if processos:
            scores = [p.score_auditoria for p in processos if p.score_auditoria is not None]
            media_score = sum(scores) / len(scores) if scores else None

            print(f"         Tribunais: {tribunais} | Com partes: {com_partes}/{len(processos)} | "
                  f"Com movs: {com_movs}/{len(processos)} | Segredo: {segredos}")
            if media_score is not None:
                print(f"         Score médio de auditoria: {media_score:.1f}/100")

            # Mostrar 2 processos como amostra
            for p in processos[:2]:
                print(f"         → {p.numero_cnj} | {p.tribunal.upper()} | "
                      f"Partes: {len(p.partes)} | Movs: {len(p.movimentacoes)} | "
                      f"Situação: {p.situacao or 'N/A'}")
        else:
            print(f"         Nenhum processo encontrado (OAB pode não ter processos indexados).")

        return {
            "oab": f"{oab}/{uf}",
            "total": len(processos),
            "com_partes": com_partes,
            "com_movs": com_movs,
            "segredos": segredos,
            "tribunais": tribunais,
            "duracao": duracao,
            "erro": None,
        }

    except Exception as e:
        duracao = time.time() - inicio
        print(f"ERRO ERRO ({duracao:.1f}s): {e}")
        return {
            "oab": f"{oab}/{uf}",
            "total": 0,
            "com_partes": 0,
            "com_movs": 0,
            "segredos": 0,
            "tribunais": 0,
            "duracao": duracao,
            "erro": str(e),
        }


async def main():
    print("=" * 70)
    print("  TESTE DO SISTEMA — 10 BUSCAS COM OABs DIFERENTES")
    print("  Motor: DataJud CNJ (API pública, 90+ tribunais)")
    print("=" * 70)

    inicio_total = time.time()
    resultados = []

    async with DataJudCrawler() as crawler:
        for idx, (oab, uf) in enumerate(OABS_TESTE, 1):
            resultado = await testar_oab(crawler, oab, uf, idx)
            resultados.append(resultado)

    duracao_total = time.time() - inicio_total

    # Resumo final
    print("\n" + "=" * 70)
    print("  RESUMO FINAL")
    print("=" * 70)
    sucessos = [r for r in resultados if r["erro"] is None]
    erros    = [r for r in resultados if r["erro"] is not None]
    total_processos = sum(r["total"] for r in resultados)

    print(f"  Buscas realizadas:    10")
    print(f"  Sucessos:             {len(sucessos)}/10")
    print(f"  Erros:                {len(erros)}/10")
    print(f"  Total de processos:   {total_processos}")
    print(f"  Tempo total:          {duracao_total:.1f}s")
    print(f"  Tempo médio/busca:    {duracao_total/10:.1f}s")

    if erros:
        print(f"\n  Erros encontrados:")
        for r in erros:
            print(f"    - OAB {r['oab']}: {r['erro']}")

    print("\n  OABs com mais processos:")
    for r in sorted(sucessos, key=lambda x: x["total"], reverse=True)[:3]:
        print(f"    {r['oab']}: {r['total']} processo(s) em {r['tribunais']} tribunal(is)")

    media_com_partes = sum(r["com_partes"] for r in sucessos) / max(total_processos, 1) * 100
    media_com_movs   = sum(r["com_movs"] for r in sucessos) / max(total_processos, 1) * 100
    print(f"\n  Qualidade dos dados extraídos:")
    print(f"    Processos com partes:        {media_com_partes:.1f}%")
    print(f"    Processos com movimentações: {media_com_movs:.1f}%")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
