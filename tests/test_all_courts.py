"""
Teste completo de todos os tribunais brasileiros.
Identifica quais crawlers funcionam e quais precisam de correção.
"""
import asyncio
import time
from collections import defaultdict

# OAB de teste (uma que sabemos que tem processos no TJSP)
OAB_TESTE = "112859"  # OAB que teve 25 processos no TJSP
UF_TESTE = "SP"

# Tribunais por tipo de sistema
SISTEMAS = {
    "PJe": {
        "tribunais": [
            # TRTs (Trabalhista)
            ("trt1", "TRT 1ª Região (RJ)"),
            ("trt2", "TRT 2ª Região (SP)"),
            ("trt3", "TRT 3ª Região (MG)"),
            ("trt4", "TRT 4ª Região (RS)"),
            ("trt5", "TRT 5ª Região (BA)"),
            ("trt6", "TRT 6ª Região (PE)"),
            ("trt7", "TRT 7ª Região (CE)"),
            ("trt8", "TRT 8ª Região (PA/AP)"),
            ("trt9", "TRT 9ª Região (PR)"),
            ("trt10", "TRT 10ª Região (DF/TO)"),
            ("trt11", "TRT 11ª Região (AM)"),
            ("trt12", "TRT 12ª Região (SC)"),
            ("trt13", "TRT 13ª Região (PB)"),
            ("trt14", "TRT 14ª Região (RO)"),
            ("trt15", "TRT 15ª Região (SP)"),
            ("trt16", "TRT 16ª Região (MA)"),
            ("trt17", "TRT 17ª Região (ES)"),
            ("trt18", "TRT 18ª Região (GO)"),
            ("trt19", "TRT 19ª Região (AL)"),
            ("trt20", "TRT 20ª Região (SE)"),
            ("trt21", "TRT 21ª Região (RN)"),
            ("trt22", "TRT 22ª Região (PI)"),
            ("trt23", "TRT 23ª Região (MT)"),
            ("trt24", "TRT 24ª Região (MS)"),
            # Tribunal Superior
            ("tst", "Tribunal Superior do Trabalho"),
            # TJs via PJe
            ("tjba", "TJ Bahia"),
            ("tjpe", "TJ Pernambuco"),
            ("tjce", "TJ Ceará"),
            ("tjrn", "TJ Rio Grande do Norte"),
            ("tjma", "TJ Maranhão"),
            ("tjpi", "TJ Piauí"),
            ("tjdft", "TJ Distrito Federal"),
        ]
    },
    "eProc": {
        "tribunais": [
            ("trf1", "TRF 1ª Região"),
            ("trf4", "TRF 4ª Região"),
            ("tjal", "TJ Alagoas"),
            ("tjse", "TJ Sergipe"),
            ("tjam", "TJ Amazonas"),
            ("tjro", "TJ Rondônia"),
            ("tjac", "TJ Acre"),
        ]
    },
    "ESAJ": {
        "tribunais": [
            ("tjsp", "TJ São Paulo"),
            ("tjrj", "TJ Rio de Janeiro"),
            ("tjmg", "TJ Minas Gerais"),
            ("tjpr", "TJ Paraná"),
            ("tjsc", "TJ Santa Catarina"),
            ("tjrs", "TJ Rio Grande do Sul"),
            ("tjgo", "TJ Goiás"),
            ("tjce", "TJ Ceará"),
            ("tjpe", "TJ Pernambuco"),
            ("tjba", "TJ Bahia"),
        ]
    },
    "STJ_STF": {
        "tribunais": [
            ("stj", "Superior Tribunal de Justiça"),
        ]
    }
}


async def testar_pje(tribunal, nome):
    """Testa crawler PJe."""
    try:
        from src.crawlers.pje import PJeCrawler
        async with PJeCrawler(verify_ssl=False) as crawler:
            result = await crawler.buscar_por_oab(
                OAB_TESTE, UF_TESTE, tribunais=[tribunal], tamanho=10
            )
            return len(result), None
    except Exception as e:
        return 0, str(e)[:100]


async def testar_eproc(tribunal, nome):
    """Testa crawler eProc."""
    try:
        from src.crawlers.eproc import EProcCrawler
        async with EProcCrawler(verify_ssl=False) as crawler:
            result = await crawler.buscar_por_oab(
                OAB_TESTE, UF_TESTE, tribunais=[tribunal], paginas=1
            )
            return len(result), None
    except Exception as e:
        return 0, str(e)[:100]


async def testar_esaj(tribunal, nome):
    """Testa crawler eSAJ genérico."""
    try:
        from src.crawlers.esaj_generico import ESajMultiCrawler
        async with ESajMultiCrawler() as crawler:
            result = await crawler.buscar_por_oab(
                OAB_TESTE, UF_TESTE, tribunais=[tribunal], paginas=1
            )
            return len(result), None
    except Exception as e:
        return 0, str(e)[:100]


async def testar_stj(tribunal, nome):
    """Testa crawler STJ."""
    try:
        from src.crawlers.stj import STJCrawler
        async with STJCrawler(verify_ssl=False) as crawler:
            result = await crawler.buscar_por_oab(OAB_TESTE, UF_TESTE)
            return len(result), None
    except Exception as e:
        return 0, str(e)[:100]


async def testar_tst(tribunal, nome):
    """Testa crawler TST."""
    try:
        from src.crawlers.tst import TSTCrawler
        async with TSTCrawler(verify_ssl=False) as crawler:
            result = await crawler.buscar_por_oab(OAB_TESTE, UF_TESTE)
            return len(result), None
    except Exception as e:
        return 0, str(e)[:100]


async def testar_tjsp(tribunal, nome):
    """Testa crawler TJSP específico."""
    try:
        from src.crawlers.tjsp import TJSPCrawler
        async with TJSPCrawler() as crawler:
            result = await crawler.buscar_por_oab(OAB_TESTE, UF_TESTE, paginas=1)
            return len(result), None
    except Exception as e:
        return 0, str(e)[:100]


async def testar_tjmg(tribunal, nome):
    """Testa crawler TJMG."""
    try:
        from src.crawlers.tjmg import TJMG_UnifiedCrawler
        async with TJMG_UnifiedCrawler() as crawler:
            result = await crawler.buscar_por_oab(OAB_TESTE, UF_TESTE)
            return len(result), None
    except Exception as e:
        return 0, str(e)[:100]


FUNCOES_TESTE = {
    "PJe": testar_pje,
    "eProc": testar_eproc,
    "ESAJ": testar_esaj,
    "STJ_STF": testar_stj,
}


async def main():
    print("=" * 70)
    print("TESTE COMPLETO DE TODOS OS TRIBUNAIS BRASILEIROS")
    print("=" * 70)
    print(f"OAB de teste: {OAB_TESTE}/{UF_TESTE}")
    print()

    resultados = defaultdict(list)
    erros_por_sistema = defaultdict(list)

    for sistema, tribunais in SISTEMAS.items():
        print(f"\n{'='*70}")
        print(f"TESTANDO: {sistema}")
        print(f"{'='*70}")

        funcao_teste = FUNCOES_TESTE.get(sistema, testar_pje)

        for tribunal, nome in tribunais:
            print(f"[{tribunal:8}] {nome:40}", end=" ", flush=True)

            # Casos especiais
            if tribunal == "tjsp":
                qtd, erro = await testar_tjsp(tribunal, nome)
            elif tribunal == "tjmg":
                qtd, erro = await testar_tjmg(tribunal, nome)
            elif tribunal == "tst":
                qtd, erro = await testar_tst(tribunal, nome)
            else:
                qtd, erro = await funcao_teste(tribunal, nome)

            if erro:
                print(f"❌ ERRO: {erro}")
                erros_por_sistema[sistema].append((tribunal, nome, erro))
            elif qtd > 0:
                print(f"✅ {qtd} processos")
                resultados[sistema].append((tribunal, nome, qtd))
            else:
                print(f"⚪ 0 processos (OK mas sem dados)")

            await asyncio.sleep(0.5)

    # Resumo
    print()
    print("=" * 70)
    print("RESUMO GERAL")
    print("=" * 70)

    total_funcionando = 0
    total_erro = 0

    for sistema in SISTEMAS:
        funcionando = resultados[sistema]
        erros = erros_por_sistema[sistema]

        print(f"\n{sistema}:")
        print(f"  ✅ Funcionando: {len(funcionando)}")
        print(f"  ❌ Erro: {len(erros)}")

        if funcionando:
            print(f"  Tribunais: {', '.join([t[0] for t in funcionando])}")

        if erros:
            print(f"  Com erro: {', '.join([t[0] for t in erros])}")

        total_funcionando += len(funcionando)
        total_erro += len(erros)

    total_tribunais = sum(len(t[1]) for t in SISTEMAS.items())

    print()
    print("=" * 70)
    print(f"TOTAIS: {total_funcionando}/{total_tribunais} funcionando")
    print("=" * 70)

    if erros_por_sistema:
        print("\nPRÓXIMOS PASSOS - Corrigir estes tribunais:")
        for sistema, erros in erros_por_sistema.items():
            print(f"\n{sistema}:")
            for tribunal, nome, erro in erros:
                print(f"  - {tribunal} ({nome}): {erro}")


if __name__ == "__main__":
    asyncio.run(main())
