
import asyncio
import aiohttp
import time
import json

URL = "https://juridico-crawler-production.up.railway.app/api/integracao/oab"

# Lista de 50 OABs e Nomes para teste de estresse
TEST_CASES = [
    {"num": "202030", "uf": "MG", "nome": "PELICIONI", "desc": "Caso Real Julia MG"},
    {"num": "100000", "uf": "MG", "nome": "PEREIRA", "desc": "MG 1"},
    {"num": "150000", "uf": "MG", "nome": "SANTOS", "desc": "MG 2"},
    {"num": "180000", "uf": "MG", "nome": "FERREIRA", "desc": "MG 3"},
    {"num": "210000", "uf": "MG", "nome": "SILVA", "desc": "MG 4"},
    
    {"num": "300000", "uf": "SP", "nome": "FERNANDES", "desc": "SP 1"},
    {"num": "350000", "uf": "SP", "nome": "OLIVEIRA", "desc": "SP 2"},
    {"num": "400000", "uf": "SP", "nome": "ALMEIDA", "desc": "SP 3"},
    {"num": "450000", "uf": "SP", "nome": "COSTA", "desc": "SP 4"},
    {"num": "250000", "uf": "SP", "nome": "MATOS", "desc": "SP 5"},
    
    {"num": "50000", "uf": "RJ", "nome": "GOMES", "desc": "RJ 1"},
    {"num": "80000", "uf": "RJ", "nome": "ROCHA", "desc": "RJ 2"},
    {"num": "100000", "uf": "RJ", "nome": "MARTINS", "desc": "RJ 3"},
    {"num": "120000", "uf": "RJ", "nome": "LIMA", "desc": "RJ 4"},
    {"num": "150000", "uf": "RJ", "nome": "CARVALHO", "desc": "RJ 5"},
    
    {"num": "40000", "uf": "RS", "nome": "TEIXEIRA", "desc": "RS 1"},
    {"num": "70000", "uf": "RS", "nome": "MOREIRA", "desc": "RS 2"},
    {"num": "90000", "uf": "RS", "nome": "RIBEIRO", "desc": "RS 3"},
    {"num": "100000", "uf": "RS", "nome": "MACHADO", "desc": "RS 4"},
    {"num": "120000", "uf": "RS", "nome": "BARBOSA", "desc": "RS 5"},
    
    {"num": "30000", "uf": "DF", "nome": "MENDES", "desc": "DF 1"},
    {"num": "45000", "uf": "DF", "nome": "CAVALCANTE", "desc": "DF 2"},
    {"num": "60000", "uf": "DF", "nome": "ARAUJO", "desc": "DF 3"},
    {"num": "15000", "uf": "DF", "nome": "XAVIER", "desc": "DF 4"},
    {"num": "42000", "uf": "DF", "nome": "FREITAS", "desc": "DF 5"},

    # Casos 26-50 (Variados)
    {"num": "200000", "uf": "PR", "nome": "DIAS", "desc": "PR 1"},
    {"num": "180000", "uf": "PR", "nome": "PINTO", "desc": "PR 2"},
    {"num": "120000", "uf": "PR", "nome": "SOUSA", "desc": "PR 3"},
    {"num": "60000", "uf": "SC", "nome": "VIEIRA", "desc": "SC 1"},
    {"num": "80000", "uf": "SC", "nome": "NUNES", "desc": "SC 2"},
    {"num": "40000", "uf": "SC", "nome": "MORAES", "desc": "SC 3"},
    {"num": "100000", "uf": "BA", "nome": "DUARTE", "desc": "BA 1"},
    {"num": "120000", "uf": "BA", "nome": "MARQUES", "desc": "BA 2"},
    {"num": "75000", "uf": "BA", "nome": "BRANDAO", "desc": "BA 3"},
    {"num": "55000", "uf": "PE", "nome": "NASCIMENTO", "desc": "PE 1"},
    {"num": "85000", "uf": "PE", "nome": "RAMOS", "desc": "PE 2"},
    {"num": "95000", "uf": "PE", "nome": "CALDAS", "desc": "PE 3"},
    {"num": "33000", "uf": "ES", "nome": "REIS", "desc": "ES 1"},
    {"num": "44000", "uf": "ES", "nome": "LEAL", "desc": "ES 2"},
    {"num": "22000", "uf": "GO", "nome": "PAIVA", "desc": "GO 1"},
    {"num": "44000", "uf": "GO", "nome": "GUIMARAES", "desc": "GO 2"},
    {"num": "33000", "uf": "CE", "nome": "ANDRADE", "desc": "CE 1"},
    {"num": "55000", "uf": "CE", "nome": "BRITO", "desc": "CE 2"},
    {"num": "33000", "uf": "RN", "nome": "CORREIA", "desc": "RN 1"},
    {"num": "22000", "uf": "PB", "nome": "MONTEIRO", "desc": "PB 1"},
    {"num": "66000", "uf": "MT", "nome": "CARDOSO", "desc": "MT 1"},
    {"num": "44000", "uf": "MS", "nome": "FIGUEIREDO", "desc": "MS 1"},
    {"num": "12000", "uf": "AM", "nome": "FARIAS", "desc": "AM 1"},
    {"num": "55000", "uf": "PA", "nome": "BARROS", "desc": "PA 1"},
    {"num": "33000", "uf": "MA", "nome": "LOPES", "desc": "MA 1"}
]

async def run_test(session, case, semaphore):
    async with semaphore:
        print(f"🚀 Iniciando ({case['desc']}): {case['num']}/{case['uf']} - Nome: {case['nome']}")
        start = time.time()
        payload = {
            "numero_oab": case['num'],
            "uf_oab": case['uf'],
            "nome_advogado": case['nome']
        }
        try:
            async with session.post(URL, json=payload, timeout=180) as resp:
                data = await resp.json()
                duration = time.time() - start
                count = len(data.get('processos', []))
                print(f"✅ Concluído ({case['desc']}) | Encontrados: {count} | Tempo: {duration:.2f}s")
                return {"desc": case['desc'], "success": True, "count": count, "duration": duration}
        except Exception as e:
            print(f"❌ Falha ({case['desc']}) | Erro: {str(e)}")
            return {"desc": case['desc'], "success": False, "error": str(e)}

async def main():
    print(f"--- MEGA TESTE DE CARGA: 50 BUSCAS EM LOTES ---\n")
    semaphore = asyncio.Semaphore(5) # Processa 5 por vez para não ser bloqueado
    async with aiohttp.ClientSession() as session:
        tasks = [run_test(session, case, semaphore) for case in TEST_CASES]
        results = await asyncio.gather(*tasks)
    
    print(f"\n--- RELATÓRIO FINAL ---")
    sucesso = sum(1 for r in results if r.get('success'))
    total_proc = sum(r.get('count', 0) for r in results if r.get('success'))
    tempo_medio = sum(r.get('duration', 0) for r in results if r.get('success')) / (sucesso or 1)
    
    print(f"Buscas Realizadas: {len(results)}")
    print(f"Sucesso (200 OK): {sucesso}/{len(results)}")
    print(f"Total Processos Filtrados: {total_proc}")
    print(f"Tempo Médio de Resposta: {tempo_medio:.2f}s")

if __name__ == "__main__":
    asyncio.run(main())
