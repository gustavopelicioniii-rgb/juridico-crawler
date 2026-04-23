"""
Orquestrador Nativo Maestro.

Substitui a dependência do CNJ (DataJud) distribuindo as buscas massivas de OAB
inteligente e paralelamente diretamente para os scrappers nativos de cada Tribunal.
"""
import asyncio
import structlog
from typing import Optional

from src.parsers.estruturas import ProcessoCompleto

# Imports dos Crawlers Nativos
from src.crawlers.tjsp import TJSPCrawler
from src.crawlers.tjmg import TJMG_UnifiedCrawler
from src.crawlers.pje import PJeCrawler, TODOS_TRIBUNAIS_PJE
from src.crawlers.eproc import EProcCrawler, TODOS_TRIBUNAIS_EPROC
from src.crawlers.esaj_generico import ESajMultiCrawler, ESAJ_TRIBUNAIS
from src.crawlers.trf import TRFCrawler
from src.crawlers.stj import STJCrawler
from src.crawlers.tst import TSTCrawler

logger = structlog.get_logger(__name__)

class OrquestradorNativo:
    """Roteia as pesquisas de múltiplos tribunais para os motores nativos correspondentes."""
    
    def __init__(self, requests_per_minute=None, max_retries=3):
        self.rpm = requests_per_minute
        self.retries = max_retries

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        tribunais: Optional[list[str]] = None,
        max_concorrentes_orquestrador: int = 5,
        nome_advogado: str = None,
        cpf_advogado: str = None,
    ) -> list[ProcessoCompleto]:
        
        # Se tribunais é vazio, nulo ou contém "todos", assumimos a varredura completa
        TODOS_ESAJ = list(ESAJ_TRIBUNAIS.keys())
        if not tribunais or len(tribunais) == 0:
            alvos = ["tjsp", "tjmg", "stj", "tst"] + TODOS_ESAJ + TODOS_TRIBUNAIS_PJE + TODOS_TRIBUNAIS_EPROC + ["trf1", "trf2", "trf3", "trf4", "trf5"]
            logger.info("Tribunais não especificados ou lista vazia. Assumindo varredura em 'Todos'.")
        else:
            alvos = [t.lower().strip() for t in tribunais if t]
            if not alvos:
                alvos = ["tjsp", "tjmg", "stj", "tst"] + TODOS_ESAJ + TODOS_TRIBUNAIS_PJE + TODOS_TRIBUNAIS_EPROC + ["trf1", "trf2", "trf3", "trf4", "trf5"]

        logger.info(f"Orquestrador Master Iniciando varredura para OAB {numero_oab}/{uf_oab} em {len(alvos)} alvos (Filtro nome: {nome_advogado or 'Nenhum'}, CPF: {cpf_advogado or 'Nenhum'})...")

        # Categorizar os alvos por Crawler Responsável
        alvos_tjsp = []
        alvos_tjmg = []
        alvos_pje = []
        alvos_eproc = []
        alvos_esaj = []
        alvos_trf = []
        usar_stj = False
        usar_tst = False

        for t in alvos:
            if t == "tjsp":
                alvos_tjsp.append(t)
            elif t == "tjmg":
                alvos_tjmg.append(t)
            elif t == "stj":
                usar_stj = True
            elif t == "tst":
                usar_tst = True
            elif t in ESAJ_TRIBUNAIS:
                alvos_esaj.append(t)
            elif t.startswith("trf") and t in ("trf1", "trf2", "trf3", "trf4", "trf5"):
                alvos_trf.append(t)
            elif t in TODOS_TRIBUNAIS_PJE:
                alvos_pje.append(t)
            elif t in TODOS_TRIBUNAIS_EPROC:
                alvos_eproc.append(t)
            else:
                logger.warning(f"Tribunal {t} não suportado ainda por um motor nativo.")

        # Tarefas assíncronas do super-orquestrador
        tasks = []
        
        async def scrape_tjsp():
            if not alvos_tjsp: return []
            try:
                # TJSP não tem API de OAB, mas podemos tentar passar o campo se suportado no futuro
                async with TJSPCrawler() as crawler:
                    return await crawler.buscar_por_oab(numero_oab, uf_oab, paginas=5)
            except Exception as e:
                logger.error(f"Erro TJSP: {e}")
                return []

        async def scrape_tjmg():
            if not alvos_tjmg: return []
            try:
                async with TJMG_UnifiedCrawler() as crawler:
                    return await crawler.buscar_por_oab(numero_oab, uf_oab, cpf_advogado=cpf_advogado)
            except Exception as e:
                logger.error(f"Erro TJMG: {e}")
                return []

        async def scrape_pje():
            if not alvos_pje: return []
            try:
                async with PJeCrawler(verify_ssl=False) as crawler:
                    return await crawler.buscar_por_oab(
                        numero_oab=numero_oab, 
                        uf_oab=uf_oab, 
                        tribunais=alvos_pje, 
                        tamanho=100, 
                        cpf_advogado=cpf_advogado
                    )
            except Exception as e:
                logger.error(f"Erro PJe: {e}")
                return []

        async def scrape_eproc():
            if not alvos_eproc: return []
            try:
                async with EProcCrawler(verify_ssl=False) as crawler:
                    return await crawler.buscar_por_oab(
                        numero_oab=numero_oab, 
                        uf_oab=uf_oab, 
                        tribunais=alvos_eproc, 
                        paginas=5, 
                        cpf_advogado=cpf_advogado
                    )
            except Exception as e:
                logger.error(f"Erro eProc: {e}")
                return []

        async def scrape_esaj():
            if not alvos_esaj: return []
            try:
                async with ESajMultiCrawler() as crawler:
                    return await crawler.buscar_por_oab(numero_oab, uf_oab, tribunais=alvos_esaj, paginas=3)
            except Exception as e:
                logger.error(f"Erro eSAJ multi: {e}")
                return []

        async def scrape_trf():
            if not alvos_trf: return []
            try:
                async with TRFCrawler(verify_ssl=False) as crawler:
                    return await crawler.buscar_por_oab(numero_oab, uf_oab, tribunais=alvos_trf)
            except Exception as e:
                logger.error(f"Erro TRF: {e}")
                return []

        async def scrape_stj():
            if not usar_stj: return []
            try:
                async with STJCrawler(verify_ssl=False) as crawler:
                    return await crawler.buscar_por_oab(numero_oab, uf_oab)
            except Exception as e:
                logger.error(f"Erro STJ: {e}")
                return []

        async def scrape_tst():
            if not usar_tst: return []
            try:
                async with TSTCrawler(verify_ssl=False) as crawler:
                    return await crawler.buscar_por_oab(numero_oab, uf_oab)
            except Exception as e:
                logger.error(f"Erro TST: {e}")
                return []

        # Empacotamos todas as frentes de batalha
        tasks.append(scrape_tjsp())
        tasks.append(scrape_tjmg())
        tasks.append(scrape_pje())
        tasks.append(scrape_eproc())
        tasks.append(scrape_esaj())
        tasks.append(scrape_trf())
        tasks.append(scrape_stj())
        tasks.append(scrape_tst())

        try:
            resultados_nested = await asyncio.gather(*tasks, return_exceptions=True)
            
            processos_consolidados = []
            for resultado in resultados_nested:
                if isinstance(resultado, Exception):
                    logger.error(f"Erro em sub-orquestrador: {resultado}")
                elif isinstance(resultado, list):
                    processos_consolidados.extend(resultado)

            # Deduplicar
            unicos = {p.numero_cnj: p for p in processos_consolidados}
            processos_coletados = list(unicos.values())
            
            # FILTRAGEM DE ALTA PRECISÃO (CPF e/ou NOME)
            if (nome_advogado or cpf_advogado) and processos_coletados:
                import unicodedata
                import re

                def normalizar(txt):
                    if not txt: return ""
                    return "".join(
                        c for c in unicodedata.normalize('NFD', txt.upper())
                        if unicodedata.category(c) != 'Mn'
                    ).strip()

                def limpar_cpf(c):
                    if not c: return ""
                    return re.sub(r'\D', '', c)

                nome_alvo = normalizar(nome_advogado) if nome_advogado else None
                cpf_alvo = limpar_cpf(cpf_advogado) if cpf_advogado else None
                
                processos_filtrados = []
                for p in processos_coletados:
                    match = False
                    for parte in p.partes:
                        # 1. Tenta por CPF (é a prova cabal)
                        if cpf_alvo and parte.documento:
                            if limpar_cpf(parte.documento) == cpf_alvo:
                                match = True
                                break
                        
                        # 2. Tenta por Nome/Sobrenome
                        if nome_alvo and parte.nome:
                            if nome_alvo in normalizar(parte.nome):
                                match = True
                                break
                    
                    if match:
                        processos_filtrados.append(p)
                    else:
                        logger.info(f"Processo {p.numero_cnj} descartado: não atende aos filtros de precisão (Nome: {nome_alvo}, CPF: {cpf_alvo}).")
                
                processos_coletados = processos_filtrados

            # ===== INÍCIO DA AUDITORIA EM TEMPO REAL =====
            for p in processos_coletados:
                pontos = 100
                notas = []
                
                # 1. Metadados básicos
                if not p.numero_cnj:
                    notas.append("[ERRO] Número CNJ ausente.")
                    pontos -= 30
                if not p.tribunal:
                    notas.append("[ERRO] Tribunal ausente.")
                    pontos -= 10
                    
                if not p.classe_processual:
                    notas.append("Classe processual não identificada.")
                    pontos -= 5
                if not p.assunto:
                    notas.append("Assunto do processo em branco.")
                    pontos -= 5
                if not p.vara or not p.comarca:
                    notas.append("Vara ou Comarca ausentes.")
                    pontos -= 5
                    
                # 2. Segredo de Justiça
                if p.segredo_justica:
                    notas.append("Processo em Segredo de Justiça (omissões são normais).")
                else:
                    # 3. Partes
                    if not p.partes:
                        notas.append("[ERRO] Nenhuma parte (autor/réu) encontrada e ausência de Segredo de Justiça.")
                        pontos -= 20
                    else:
                        tipos = [pt.tipo_parte.upper() for pt in p.partes if pt.tipo_parte]
                        tem_requerente = any("REQUERENTE" in t or "AUTOR" in t or "EXEQUENTE" in t or "REQTE" in t or "EXQTE" in t or "IMPTTE" in t or "EMBTE" in t for t in tipos)
                        tem_requerido = any("REQUERIDO" in t or "REU" in t or "RÉU" in t or "EXECUTADO" in t or "REQDO" in t or "EXDO" in t or "IMPTDO" in t or "EMBDO" in t for t in tipos)
                        
                        if not (tem_requerente or tem_requerido):
                            notas.append("Polos (autor/réu) não identificados claramente.")
                            pontos -= 5
                        
                # 4. Movimentações
                if not p.movimentacoes:
                    if p.situacao and p.situacao.upper() in ["CONCLUÍDO", "BAIXADO", "EXTINTO", "ARQUIVADO"]:
                        notas.append("[ERRO] Processo marcado como concluído, mas zero movimentações lidas.")
                        pontos -= 20
                    else:
                        notas.append("Nenhuma movimentação processual encontrada.")
                        pontos -= 10
                        
                # 5. Valores
                if p.valor_causa is None:
                    notas.append("Valor da causa zerado ou ausente.")
                    pontos -= 5
                    
                p.score_auditoria = max(0, min(100, pontos))
                p.notas_auditoria = notas
            # ===== FIM DA AUDITORIA =====

            logger.info(f"Orquestrador Master Finalizado: {len(processos_coletados)} processos unicos coletados sem depender do DataJud.")
            return processos_coletados
            
        except Exception as e:
            logger.error(f"Erro no Orquestrador Master: {e}")
            return []
