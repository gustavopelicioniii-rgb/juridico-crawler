import asyncio
import sys
import os
from datetime import date
sys.path.append(os.getcwd())

from src.database.connection import AsyncSessionLocal
from src.services.processo_service import ProcessoService
from src.parsers.estruturas import ProcessoCompleto, ParteProcesso

async def force_update_sidney():
    cnjs_data = [
      {"cnj": "0027984-37.2022.8.26.0050", "status": "Suspenso"},
      {"cnj": "1002201-27.2025.8.26.0048", "status": "Em andamento"},
      {"cnj": "1005710-63.2025.8.26.0048", "status": "Em andamento"},
      {"cnj": "1002427-32.2025.8.26.0048", "status": "Em andamento"},
      {"cnj": "1000904-82.2025.8.26.0048", "status": "Em andamento"},
      {"cnj": "0009351-09.2024.8.26.0502", "status": "Em andamento"},
      {"cnj": "1007127-85.2024.8.26.0048", "status": "Em andamento"},
      {"cnj": "1500873-39.2024.8.26.0048", "status": "Em andamento"},
      {"cnj": "1003463-70.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1003032-46.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1002044-25.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1001004-08.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1001002-38.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1010317-09.2022.8.26.0048", "status": "Em andamento"},
      {"cnj": "1004313-27.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1006900-32.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1001569-71.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1006456-96.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1004551-46.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1003004-78.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1004300-28.2023.8.26.0048", "status": "Em andamento"},
      {"cnj": "1500595-75.2019.8.26.0545", "status": "Suspenso"},
      {"cnj": "1500584-66.2019.8.26.0545", "status": "Em andamento"},
      {"cnj": "1501168-52.2019.8.26.0545", "status": "Em andamento"},
      {"cnj": "1002888-43.2021.8.26.0048", "status": "Em andamento"},
      {"cnj": "1011983-70.2023.8.26.0099", "status": "Em andamento"},
      {"cnj": "1010451-61.2023.8.26.0099", "status": "Em andamento"},
      {"cnj": "1001956-62.2022.8.26.0099", "status": "Em andamento"},
      {"cnj": "0010863-87.2015.8.26.0099", "status": "Suspenso"},
      {"cnj": "1500584-61.2024.8.26.0548", "status": "Em andamento"},
      {"cnj": "1000484-17.2024.8.26.0338", "status": "Em andamento"},
      {"cnj": "0005704-51.2022.8.26.0048", "status": "Em andamento"},
      {"cnj": "1002817-49.2018.8.26.0338", "status": "Em andamento"},
      {"cnj": "1501395-93.2025.8.26.0545", "status": "Em andamento"},
      {"cnj": "1001438-18.2024.8.26.0450", "status": "Em andamento"},
      {"cnj": "1001570-12.2023.8.26.0450", "status": "Em andamento"},
      {"cnj": "1006992-39.2025.8.26.0048", "status": "Em andamento"},
      {"cnj": "1013726-03.2019.8.26.0020", "status": "Extinto"},
      {"cnj": "1502402-23.2025.8.26.0545", "status": "Em andamento"}
    ]
    
    oab = "361329"
    uf = "SP"
    
    async with AsyncSessionLocal() as db:
        svc = ProcessoService(db)
        
        procs_to_save = []
        for item in cnjs_data:
            p = ProcessoCompleto(
                numero_cnj=item["cnj"],
                tribunal="tjsp",
                situacao=item["status"].upper(),
                partes=[
                    ParteProcesso(nome="SIDNEY DA SILVA", oab=f"{oab}{uf}", tipo_parte="ADVOGADO", polo="ATIVO")
                ],
                movimentacoes=[] # Serao preenchidas no proximo sync
            )
            procs_to_save.append(p)
            
        print(f"Injetando {len(procs_to_save)} processos validados para OAB {oab}...")
        stats = await svc.salvar_processos(procs_to_save)
        print(f"Sucesso: {stats['novos']} novos, {stats['atualizados']} atualizados.")
        
        # Registra no catalogo
        await svc.registrar_advogado_descoberto(oab, uf, "SIDNEY DA SILVA (VALIDADO)", total_processos=len(procs_to_save))
        await db.commit()

if __name__ == "__main__":
    asyncio.run(force_update_sidney())
