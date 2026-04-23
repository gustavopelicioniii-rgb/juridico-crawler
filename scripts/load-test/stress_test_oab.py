
import asyncio
import aiohttp
import time
import json

URL = "https://juridico-crawler-production.up.railway.app/api/integracao/oab"

TEST_CASES = [
    {"numero_oab": "202030", "uf_oab": "MG", "nome_advogado": "JULIA", "desc": "Caso Dra. Julia"},
    {"numero_oab": "361329", "uf_oab": "SP", "nome_advogado": "FABIANO", "desc": "Outro Advogado SP"},
    {"numero_oab": "100000", "uf_oab": "MG", "nome_advogado": "PEREIRA", "desc": "OAB MG Comum"},
    {"numero_oab": "123456", "uf_oab": "SP", "nome_advogado": "SILVA", "desc": "OAB SP Comum"},
    {"numero_oab": "50000", "uf_oab": "RJ", "nome_advogado": "OLIVEIRA", "desc": "OAB RJ"},
    {"numero_oab": "200000", "uf_oab": "RS", "nome_advogado": "SANTOS", "desc": "OAB RS"},
    {"numero_oab": "150000", "uf_oab": "PR", "nome_advogado": "SOUZA", "desc": "OAB PR"},
    {"numero_oab": "80000", "uf_oab": "BA", "nome_advogado": "COSTA", "desc": "OAB BA"},
    {"numero_oab": "90000", "uf_oab": "PE", "nome_advogado": "RODRIGUES", "desc": "OAB PE"},
    {"numero_oab": "110000", "uf_oab": "SC", "nome_advogado": "FERREIRA", "desc": "OAB SC"}
]

async def run_test(session, case):
    print(f"🚀 Iniciando: {case['desc']} ({case['numero_oab']}/{case['uf_oab']})")
    start = time.time()
    try:
        async with session.post(URL, json=case, timeout=165) as resp:
            status = resp.status
            data = await resp.json()
            duration = time.time() - start
            count = len(data.get('processos', []))
            print(f"✅ Fim: {case['desc']} | Status: {status} | Encontrados: {count} | Tempo: {duration:.2f}s")
            return {"case": case['desc'], "status": status, "count": count, "duration": duration}
    except Exception as e:
        print(f"❌ Erro: {case['desc']} | {str(e)}")
        return {"case": case['desc'], "status": "error", "error": str(e)}

async def main():
    print(f"--- INICIANDO TESTE DE ESTRESSE: 10 BUSCAS PARALELAS ---\n")
    async with aiohttp.ClientSession() as session:
        tasks = [run_test(session, case) for case in TEST_CASES]
        results = await asyncio.gather(*tasks)
    
    print(f"\n--- RELATÓRIO FINAL ---")
    total_found = sum(r.get('count', 0) for r in results if r['status'] == 200)
    print(f"Total de buscas com sucesso: {sum(1 for r in results if r['status'] == 200)}/10")
    print(f"Total de processos filtrados e capturados: {total_found}")

if __name__ == "__main__":
    asyncio.run(main())
