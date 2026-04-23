import asyncio
import httpx
from selectolax.parser import HTMLParser

async def inspect_ids():
    cnj = '1003032-46.2023.8.26.0048'
    url = f"https://esaj.tjsp.jus.br/cpopg/show.do?processo.numero={cnj}&processo.foro=48"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        tree = HTMLParser(resp.text)
        
        print("Tabelas encontradas:")
        for table in tree.css("table"):
            tid = table.attributes.get("id")
            if tid:
                print(f"- ID: {tid}")
        
        print("\nClasses .nomeParteEAdvogado encontradas:")
        for n in tree.css(".nomeParteEAdvogado"):
            print(f"- Tag: {n.tag}, Texto: {n.text(strip=True)[:50]}...")

if __name__ == "__main__":
    asyncio.run(inspect_ids())
