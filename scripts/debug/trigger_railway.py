import httpx
import asyncio

async def trigger_railway_sync():
    url = "https://juridico-crawler-production.up.railway.app/api/integracao/oab"
    payload = {
        "numero_oab": "361329",
        "uf_oab": "SP",
        "nome_advogado": "SIDNEY DA SILVA"
    }
    
    print(f"Triggering sync on Railway: {url}...")
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(trigger_railway_sync())
