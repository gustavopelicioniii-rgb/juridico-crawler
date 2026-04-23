"""
Teste de stress com 50 OABs aleatórias.
Valida se os crawlers tão funcionando corretamente.
"""
import asyncio
import random
import time
from collections import defaultdict

# Tribunais pra testar
TRIBUNAIS = ["tjsp", "tjrj", "trt2", "trf3", "stj", "tst"]


def gerar_oabs(qtd=50):
    """Gera OABs aleatórias de 6 dígitos."""
    oabs = set()
    while len(oabs) < qtd:
        num = str(random.randint(100000, 999999))
        oabs.add(num)
    return list(oabs)


async def testar_oab(session, numero, uf="SP"):
    """Testa uma OAB e retorna o resultado."""
    try:
        # Import dentro da função pra evitar problemas
        from src.crawlers.orquestrador import OrquestradorNativo
        
        orq = OrquestradorNativo()
        start = time.time()
        result = await orq.buscar_por_oab(
            numero_oab=numero,
            uf_oab=uf,
            tribunais=["tjsp"],  # Começa só com TJSP
        )
        duration = time.time() - start
        
        return {
            "oab": numero,
            "resultados": len(result),
            "tempo": round(duration, 2),
            "sucesso": True,
            "erro": None,
        }
    except Exception as e:
        return {
            "oab": numero,
            "resultados": 0,
            "tempo": 0,
            "sucesso": False,
            "erro": str(e)[:100],
        }


async def main():
    print("=" * 60)
    print("TESTE DE STRESS - 50 OABs ALEATÓRIAS")
    print("=" * 60)
    print()
    
    # Gera 50 OABs aleatórias
    oabs = gerar_oabs(50)
    print(f"Geradas {len(oabs)} OABs aleatórias")
    print(f"Exemplos: {oabs[:5]}")
    print()
    
    # Testa uma por uma
    resultados = []
    erros = []
    
    print("Iniciando testes...")
    print("-" * 40)
    
    for i, oab in enumerate(oabs, 1):
        print(f"[{i:2d}/50] Testando OAB {oab}...", end=" ")
        
        result = await testar_oab(None, oab)
        resultados.append(result)
        
        if result["sucesso"]:
            print(f"✅ {result['resultados']} processos em {result['tempo']}s")
        else:
            print(f"❌ Erro: {result['erro']}")
            erros.append(result)
        
        # Rate limit pra não sobrecarregar
        await asyncio.sleep(0.5)
    
    print()
    print("=" * 60)
    print("RESUMO DOS TESTES")
    print("=" * 60)
    
    total = len(resultados)
    sucessos = sum(1 for r in resultados if r["sucesso"])
    falhas = sum(1 for r in resultados if not r["sucesso"])
    com_resultados = sum(1 for r in resultados if r["resultados"] > 0)
    total_processos = sum(r["resultados"] for r in resultados)
    tempo_medio = sum(r["tempo"] for r in resultados if r["tempo"] > 0) / max(1, total)
    
    print(f"Total de OABs testadas: {total}")
    print(f"Sucessos: {sucessos}")
    print(f"Falhas: {falhas}")
    print(f"Com resultados: {com_resultados}")
    print(f"Total de processos encontrados: {total_processos}")
    print(f"Tempo médio por OAB: {tempo_medio:.2f}s")
    
    if erros:
        print()
        print("ERROS ENCONTRADOS:")
        for e in erros[:5]:  # Mostra só os primeiros 5
            print(f"  - OAB {e['oab']}: {e['erro']}")
    
    print()
    print("=" * 60)
    print("TESTE CONCLUÍDO!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
