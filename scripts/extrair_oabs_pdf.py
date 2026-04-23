#!/usr/bin/env python3
"""Extrai OABs do PDF e salva para teste."""
import re
import sys
import json
sys.path.insert(0, '.')

from PyPDF2 import PdfReader

PDF_PATH = '/root/.openclaw/media/inbound/aobs_brasil---2de4a99d-8718-4e27-94ac-0d12f4416c5a.pdf'

# Mapeamento deUF -> texto no PDF
ESTADOS_MARKERS = {
    "AC": "OAB / AC", "AL": "OAB / AL", "AM": "OAB / AM", "AP": "OAB / AP",
    "BA": "OAB / BA", "CE": "OAB / CE", "DF": "OAB / DF", "ES": "OAB / ES",
    "GO": "OAB / GO", "MA": "OAB / MA", "MT": "OAB / MT", "MS": "OAB / MS",
    "MG": "OAB / MG", "PA": "OAB / PA", "PB": "OAB / PB", "PR": "OAB / PR",
    "PE": "OAB / PE", "PI": "OAB / PI", "RJ": "OAB / RJ", "RN": "OAB / RN",
    "RS": "OAB / RS", "RO": "OAB / RO", "RR": "OAB / RR", "SC": "OAB / SC",
    "SP": "OAB / SP", "SE": "OAB / SE", "TO": "OAB / TO"
}

def main():
    print("Lendo PDF...")
    reader = PdfReader(PDF_PATH)
    print(f"Páginas: {len(reader.pages)}")
    
    current_estado = None
    oabs_por_estado = {uf: [] for uf in ESTADOS_MARKERS}
    page_count = 0
    
    for page in reader.pages:
        page_count += 1
        if page_count % 20 == 0:
            print(f"  Página {page_count}/{len(reader.pages)}...")
        text = page.extract_text() or ""
        
        for line in text.split('\n'):
            line_stripped = line.strip()
            
            # Detectar estado
            for uf, marker in ESTADOS_MARKERS.items():
                if marker in line_stripped:
                    current_estado = uf
                    break
            
            # Extrair OABs (números de 6-9 dígitos)
            if current_estado:
                oabs = re.findall(r'(\d{6,9})', line)
                for oab in oabs:
                    # Só adiciona se for 6-9 dígitos e não for ano (2019, 2020, etc)
                    if len(oab) >= 6 and oab not in oabs_por_estado[current_estado]:
                        oabs_por_estado[current_estado].append(oab)
    
    print(f"\n=== RESULTADO DA EXTRAÇÃO ===")
    total = 0
    estados_com_oabs = 0
    for uf in sorted(oabs_por_estado.keys()):
        lista = oabs_por_estado[uf]
        total += len(lista)
        if lista:
            estados_com_oabs += 1
        print(f"  {uf}: {len(lista)} OABs — exemplos: {lista[:3]}")
    print(f"\nTotal: {total} OABs em {estados_com_oabs} estados")
    
    # Selecionar 5 de cada estado
    selecionados = {}
    for uf in sorted(oabs_por_estado.keys()):
        if oabs_por_estado[uf]:
            selecionados[uf] = oabs_por_estado[uf][:5]
    
    with open('/tmp/oabs_para_teste.json', 'w') as f:
        json.dump(selecionados, f, indent=2)
    print(f"\nSalvo em /tmp/oabs_para_teste.json")
    
    return selecionados

if __name__ == "__main__":
    main()
