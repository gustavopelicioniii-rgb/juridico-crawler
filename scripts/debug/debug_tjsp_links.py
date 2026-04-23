import asyncio
import httpx
from urllib.parse import urlencode
import re

async def debug_tjsp_oab_links():
    url = "https://esaj.tjsp.jus.br/cpopg/search.do"
    params = {
        "cbPesquisa": "NUMOAB",
        "dadosConsulta.valorConsulta": "361329SP",
        "cdForo": "-1"
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    }
    
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{url}?{urlencode(params)}", headers=headers)
        html = r.text
        
        # Procura por links de processos
        # Padrão: show.do ou open.do
        links = re.findall(r'href=["\']?([^"\'>\s]*(?:show|open)\.do\?[^"\'>\s]*)["\']?', html, re.IGNORECASE)
        print(f"Total de links encontrados: {len(links)}")
        
        # Procura por CNJs
        cnjs = re.findall(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}', html)
        print(f"Total de CNJs encontrados: {len(cnjs)}")
        
        # Salva o HTML para inspeção manual se necessário
        with open("tjsp_oab_results_debug.html", "w", encoding="utf-8") as f:
            f.write(html)

if __name__ == "__main__":
    asyncio.run(debug_tjsp_oab_links())
