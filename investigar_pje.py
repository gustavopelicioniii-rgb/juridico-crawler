"""
Testa quais tribunais PJe ainda suportam busca por OAB (API ou HTML).
"""
import asyncio, httpx, re

TRIBUNAIS = {
    'trt1':  'https://pje.trt1.jus.br/consultaprocessual',
    'trt2':  'https://pje.trt2.jus.br/consultaprocessual',
    'trt3':  'https://pje.trt3.jus.br/consultaprocessual',
    'trt4':  'https://pje.trt4.jus.br/consultaprocessual',
    'trt5':  'https://pje.trt5.jus.br/consultaprocessual',
    'trt15': 'https://pje.trt15.jus.br/consultaprocessual',
    'tjba':  'https://pje.tjba.jus.br/pje',
    'tjpe':  'https://pje.tjpe.jus.br/pje',
    'tjce':  'https://pje.tjce.jus.br/pje',
    'tjmg':  'https://pje-consulta-publica.tjmg.jus.br/pje',
    'tjdft': 'https://pje.tjdft.jus.br/consultaprocessual',
}

OAB = '361329'
UF  = 'SP'

async def testar_tribunal(nome: str, base: str, c: httpx.AsyncClient):
    headers = {'User-Agent': 'Mozilla/5.0 Chrome/120.0.0.0', 'X-Grau-Instancia': '1'}
    resultados = []

    # 1. API REST antiga
    api_url = f'{base}/api/v1/advogado/{OAB}/processos'
    try:
        r = await c.get(api_url, params={'uf': UF}, headers=headers, timeout=10)
        ct = r.headers.get('content-type', '')
        if 'json' in ct and r.status_code == 200:
            d = r.json()
            n = len(d) if isinstance(d, list) else d.get('totalElements', d.get('total', '?'))
            resultados.append(f'API-JSON OK ({n} proc)')
        elif r.status_code not in (404, 405):
            resultados.append(f'API status={r.status_code}')
    except Exception as e:
        resultados.append(f'API err={type(e).__name__}')

    # 2. HTML legado consultaPublica
    html_url = f'{base}/consultaPublica/listView.seam'
    try:
        r2 = await c.get(html_url, params={'tipoConsulta': 'advogado', 'numeroOAB': OAB, 'ufOAB': UF}, headers=headers, timeout=10)
        cnjs = re.findall(r'\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}', r2.text)
        if cnjs:
            resultados.append(f'HTML-legado OK ({len(cnjs)} CNJs)')
        elif r2.status_code == 200:
            resultados.append(f'HTML-legado 200 sem CNJ ({len(r2.text)} bytes)')
        else:
            resultados.append(f'HTML-legado status={r2.status_code}')
    except Exception as e:
        resultados.append(f'HTML err={type(e).__name__}')

    return resultados

async def main():
    print('Testando suporte a busca por OAB em todos os tribunais PJe...\n')
    async with httpx.AsyncClient(verify=False, follow_redirects=True) as c:
        for nome, base in TRIBUNAIS.items():
            r = await testar_tribunal(nome, base, c)
            status = ' | '.join(r)
            funcionando = any('OK' in x for x in r)
            marca = 'OK' if funcionando else '--'
            print(f'  [{marca}] {nome.upper():8s}: {status}')

asyncio.run(main())
