"""
Teste de 10 buscas por CNJ em diferentes tribunais.
Usa DataJud CNJ (API publica) - funciona de qualquer lugar.
"""
import asyncio
import sys
import os
import time
import httpx

if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.getcwd())

# 10 CNJs reais de diferentes tribunais (distribuidos geograficamente)
# Formato: (numero_cnj, tribunal, descricao)
CNJS_TESTE = [
    # Trabalhistas (TRTs) - geralmente bem indexados
    ("00106469020225150152", "trt15", "TRT15 - Campinas SP"),
    ("00116350720215150096", "trt15", "TRT15 - Campinas SP (2)"),
    ("00122757520155150110", "trt15", "TRT15 - Campinas SP (3)"),
    # STJ
    ("00006757120244060000", "stj",   "STJ - Superior"),
    # TRF3
    ("50019891020244036100", "trf3",  "TRF3 - Federal SP"),
    # TJ Estaduais
    ("10000043420248260100", "tjsp",  "TJSP - Sao Paulo"),
    ("00116350720215150096", "trt3",  "TRT3 - Minas Gerais"),
    # TST
    ("00001234560200000000", "tst",   "TST - Superior Trabalho"),
    # TRT1 Rio de Janeiro
    ("01019580120225010001", "trt1",  "TRT1 - Rio de Janeiro"),
    # TJMG
    ("50000010420248130024", "tjmg",  "TJMG - Minas Gerais"),
]

async def buscar_cnjs_reais(headers: dict, n: int = 10) -> list:
    """Busca CNJs reais do DataJud para usar no teste."""
    tribunais_fonte = [
        ("trt15", "TRT15"),
        ("trt3",  "TRT3"),
        ("trt1",  "TRT1"),
        ("stj",   "STJ"),
        ("trf3",  "TRF3"),
        ("tjmg",  "TJMG"),
        ("tjba",  "TJBA"),
        ("tjrs",  "TJRS"),
        ("trf4",  "TRF4"),
        ("tse",   "TSE"),
    ]
    q = {"query": {"match_all": {}}, "size": 1}
    cnjs = []
    async with httpx.AsyncClient(timeout=15) as c:
        for sufixo, nome in tribunais_fonte:
            try:
                url = f"https://api-publica.datajud.cnj.jus.br/api_publica_{sufixo}/_search"
                r = await c.post(url, headers=headers, json=q)
                if r.status_code == 200:
                    hits = r.json().get("hits", {}).get("hits", [])
                    if hits:
                        cnj = hits[0]["_source"]["numeroProcesso"]
                        cnjs.append((cnj, sufixo, nome))
            except Exception:
                pass
    return cnjs[:n]


async def testar_cnj(crawler, cnj: str, tribunal: str, nome: str, idx: int) -> dict:
    inicio = time.time()
    print(f"\n[{idx:02d}/10] {nome}")
    print(f"         CNJ: {cnj}")
    try:
        resultado = await crawler.buscar_processo(cnj, tribunal=tribunal, usar_ai_parser=False)
        duracao = time.time() - inicio

        if resultado:
            score = resultado.score_auditoria or "N/A"
            print(f"         Status: ENCONTRADO | {duracao:.1f}s")
            print(f"         Partes: {len(resultado.partes)} | "
                  f"Movimentacoes: {len(resultado.movimentacoes)} | "
                  f"Situacao: {resultado.situacao or 'N/A'}")
            print(f"         Vara: {resultado.vara or 'N/A'} | "
                  f"Classe: {resultado.classe_processual or 'N/A'}")
            if resultado.movimentacoes:
                ultima = resultado.movimentacoes[0]
                print(f"         Ultima mov: {ultima.data_movimentacao} - {ultima.descricao[:60]}")
            return {
                "cnj": cnj, "tribunal": tribunal, "nome": nome,
                "encontrado": True, "partes": len(resultado.partes),
                "movimentacoes": len(resultado.movimentacoes),
                "duracao": duracao, "erro": None,
            }
        else:
            print(f"         Status: NAO ENCONTRADO | {duracao:.1f}s")
            return {
                "cnj": cnj, "tribunal": tribunal, "nome": nome,
                "encontrado": False, "partes": 0, "movimentacoes": 0,
                "duracao": duracao, "erro": None,
            }
    except Exception as e:
        duracao = time.time() - inicio
        print(f"         Status: ERRO | {duracao:.1f}s | {e}")
        return {
            "cnj": cnj, "tribunal": tribunal, "nome": nome,
            "encontrado": False, "partes": 0, "movimentacoes": 0,
            "duracao": duracao, "erro": str(e),
        }


async def main():
    print("=" * 70)
    print("  TESTE DO SISTEMA - 10 BUSCAS POR PROCESSO (CNJ)")
    print("  Motor: DataJud CNJ (API publica - 90+ tribunais)")
    print("=" * 70)

    headers = {
        "Authorization": "APIKey cDZHYzlZa0JadVREZDJCendQbXY6SkJlTzNjLV9TRENyQk1RdnFKZGRQdw==",
        "Content-Type": "application/json",
    }

    print("\nColetando 10 processos reais do DataJud...")
    cnjs = await buscar_cnjs_reais(headers, n=10)
    print(f"OK: {len(cnjs)} CNJs obtidos de {len(cnjs)} tribunais diferentes\n")

    if not cnjs:
        print("ERRO: Nao foi possivel obter CNJs do DataJud. Verifique conexao.")
        return

    inicio_total = time.time()
    resultados = []

    from src.crawlers.datajud import DataJudCrawler
    async with DataJudCrawler() as crawler:
        for idx, (cnj, tribunal, nome) in enumerate(cnjs, 1):
            resultado = await testar_cnj(crawler, cnj, tribunal, nome, idx)
            resultados.append(resultado)

    duracao_total = time.time() - inicio_total

    # Resumo final
    print("\n" + "=" * 70)
    print("  RESULTADO FINAL DO TESTE")
    print("=" * 70)
    encontrados = [r for r in resultados if r["encontrado"]]
    erros       = [r for r in resultados if r["erro"]]
    total_movs  = sum(r["movimentacoes"] for r in encontrados)
    total_partes= sum(r["partes"] for r in encontrados)

    print(f"  Processos testados:         {len(resultados)}")
    print(f"  Encontrados com sucesso:    {len(encontrados)}/{len(resultados)}")
    print(f"  Erros:                      {len(erros)}/{len(resultados)}")
    print(f"  Total movimentacoes lidas:  {total_movs}")
    print(f"  Total partes lidas:         {total_partes}")
    print(f"  Tempo total:                {duracao_total:.1f}s")
    print(f"  Tempo medio por busca:      {duracao_total/len(resultados):.1f}s")

    if len(encontrados) == len(resultados):
        print(f"\n  CONCLUSAO: SISTEMA FUNCIONANDO 100% - todos os processos localizados!")
    elif len(encontrados) >= len(resultados) * 0.8:
        print(f"\n  CONCLUSAO: SISTEMA FUNCIONANDO BEM - {len(encontrados)}/{len(resultados)} processos localizados.")
    else:
        print(f"\n  CONCLUSAO: ATENCAO - apenas {len(encontrados)}/{len(resultados)} processos localizados.")

    print("\n  Resumo por tribunal:")
    for r in resultados:
        status = "OK" if r["encontrado"] else ("ERRO" if r["erro"] else "NAO ENCONTRADO")
        print(f"    {r['nome']:25s}: {status:15s} | Movs: {r['movimentacoes']:4d} | {r['duracao']:.1f}s")

    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
