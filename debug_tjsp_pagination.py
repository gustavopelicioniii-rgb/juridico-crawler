import asyncio
import httpx
from urllib.parse import urlencode

async def check_tjsp_oab_html():
    url = "https://esaj.tjsp.jus.br/cpopg/search.do"
    params = {
        "conversationId": "",
        "dadosConsulta.localPesquisa.cdLocal": "-1",
        "cbPesquisa": "NUMOAB",
        "dadosConsulta.tipoNuProcesso": "UNIFICADO",
        "dadosConsulta.valorConsulta": "361329SP",
        "uuidCaptcha": ""
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{url}?{urlencode(params)}", headers=headers)
        html = r.text
        
        print(f"Status: {r.status_code}")
        print(f"Tamanho do HTML: {len(html)}")
        
        # Procura por marcadores de paginação
        marcas = ["Próxima", "próxima", "paginaAtual", "paginaConsulta", ">2<", "Próximo"]
        for m in marcas:
            if m in html:
                print(f"Marcador '{m}' ENCONTRADO!")
            else:
                print(f"Marcador '{m}' NÃO encontrado.")
        
        # Salva um pedaço do final do HTML onde a paginação costuma ficar
        with open("tjsp_debug_pagination.html", "w", encoding="utf-8") as f:
            f.write(html)

if __name__ == "__main__":
    asyncio.run(check_tjsp_oab_html())
