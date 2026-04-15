"""
Crawler Unificado TJMG (Tribunal de Justiça de Minas Gerais).

Este crawler orquestra a busca nos dois sistemas primários publicos do TJMG:
1. eProc (sistema atual)
2. PJe (sistema legado mas com milhões de processos ativos)

Dessa forma, contornamos a falha do CNJ de forma completa para o estado de MG.
"""
import asyncio
import logging
from typing import Optional, Any
from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import ProcessoCompleto

logger = logging.getLogger(__name__)

class TJMG_UnifiedCrawler(BaseCrawler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tribunal_id = "tjmg"

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        cpf_advogado: Optional[str] = None,
        **kwargs
    ) -> list[ProcessoCompleto]:
        
        logger.info(f"Iniciando raspagem nativa unificada TJMG para OAB {numero_oab}/{uf_oab}")
        
        from src.crawlers.eproc import EProcCrawler
        from src.crawlers.pje import PJeCrawler

        processos_totais = []

        # Instanciar crawlers base
        eproc = EProcCrawler(verify_ssl=False)
        pje = PJeCrawler(verify_ssl=False)

        async def fetch_eproc():
            try:
                # O EProcCrawler roda a varredura nativa do eproc
                return await eproc.buscar_por_oab(
                    numero_oab=numero_oab, 
                    uf_oab=uf_oab, 
                    tribunais=["tjmg"], 
                    paginas=5, 
                    cpf_advogado=cpf_advogado
                )
            except Exception as e:
                logger.error(f"Erro no eProc nativo TJMG: {e}")
                return []

        async def fetch_pje():
            try:
                # O PJeCrawler roda a varredura nativa do PJe
                return await pje.buscar_por_oab(
                    numero_oab=numero_oab, 
                    uf_oab=uf_oab, 
                    tribunais=["tjmg"], 
                    tamanho=100, 
                    cpf_advogado=cpf_advogado
                )
            except Exception as e:
                logger.error(f"Erro no PJe nativo TJMG: {e}")
                return []

        # Roda concorrentemente
        resultados = await asyncio.gather(fetch_eproc(), fetch_pje())
        
        for lista in resultados:
            processos_totais.extend(lista)

        # Deduplicação baseada no número CNJ
        unicos = {p.numero_cnj: p for p in processos_totais}
        final = list(unicos.values())
        
        logger.info(f"Varredura TJMG concluída: {len(final)} processos nativos encontrados.")
        return final

    async def buscar_processo(self, numero_cnj: str, **kwargs) -> Optional[ProcessoCompleto]:
        # Para detalhamento avulso, tenta primeiro no Eproc, depois no Pje
        from src.crawlers.eproc import EProcCrawler
        from src.crawlers.pje import PJeCrawler
        
        eproc = EProcCrawler(verify_ssl=False)
        p1 = await eproc.buscar_processo(numero_cnj, tribunal="tjmg")
        if p1 and p1.partes:
            return p1
            
        pje = PJeCrawler(verify_ssl=False)
        p2 = await pje.buscar_processo(numero_cnj, tribunal="tjmg")
        return p2
