"""
Crawler para o sistema PROJUDI (comum em PR, GO, MT, AM).

Este crawler fornece a base para consulta direta nos tribunais PROJUDI,
complementando os dados do DataJud com scraping em tempo real.

Fluxo típico do PROJUDI:
1. GET /consultaPublica/consultaPublica.do (página inicial de busca)
2. POST /consultaPublica/consultaPublica.do com parâmetros de busca (numero CNJ ou OAB)
3. O servidor retorna redirect com conversationId para a página de resultados
4. GET /consultaPublica/consultaPublica.do?conversationId=xxx&actionMethod=... (lista)
5. POST /consultaPublica/consultaPublica.do com numeroProcesso para detalhe completo
"""

import structlog
import re
from typing import Any, Optional
from datetime import datetime

from bs4 import BeautifulSoup

from src.crawlers.base import BaseCrawler
from src.parsers.estruturas import MovimentacaoProcesso, ParteProcesso, ProcessoCompleto

logger = structlog.get_logger(__name__)

PROJUDI_URLS: dict[str, str] = {
    "tjpr": "https://projudi.tjpr.jus.br/projudi",
    "tjgo": "https://projudi.tjgo.jus.br/projudi",
    "tjmt": "https://projudi.tjmt.jus.br/projudi",
    "tjam": "https://projudi.tjam.jus.br/projudi",
}

# Regex para CNJ no formato PROJUDI (geralmente só números ou com pontos/traços)
CNJ_PATTERN = re.compile(r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}")
OAB_PATTERN = re.compile(r"(\d{6,7})([A-Z]{2})", re.IGNORECASE)


class ProjudiCrawler(BaseCrawler):
    """Crawler para o sistema Projudi via portal público."""

    def _get_headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Referer": "https://www.google.com/",
        }

    async def buscar_processo(
        self,
        numero_cnj: str,
        tribunal: str,
        **kwargs: Any,
    ) -> Optional[ProcessoCompleto]:
        """
        Busca detalhe de um processo no Projudi via consulta pública.

        Fluxo:
        1. Sessão inicial para obter cookies
        2. POST de busca com número CNJ
        3. Obter lista de processos
        4. Acessar detalhe completo
        """
        base = PROJUDI_URLS.get(tribunal.lower())
        if not base:
            return None

        logger.info("Projudi %s: buscando processo %s", tribunal.upper(), numero_cnj)

        try:
            # 1. Sessão inicial
            await self._get(f"{base}/consultaPublica/consultaPublica.do")

            # 2. Busca por número de processo
            search_url = f"{base}/consultaPublica/consultaPublica.do"
            params = {
                "actionMethod": "consultaPublica:consultaProcessoAction.validarProcesso",
                "numeroProcesso": numero_cnj,
                "conversationId": "",
                "conversationId": "",
            }

            resp = await self._post(search_url, data=params)
            html = resp.text

            # 3. Extrai conversationId da resposta para próxima requisição
            conv_match = re.search(r'conversationId=([^" &]+)', html)
            conversation_id = conv_match.group(1) if conv_match else ""

            # 4. Verifica se há resultados na página
            if "Não foram encontrados" in html or "sem resultados" in html.lower():
                logger.info("Projudi %s: processo %s não encontrado", tribunal.upper(), numero_cnj)
                return None

            # 5. Tenta acessar o detalhe do processo encontrado
            processo_encontrado = self._extrair_numero_da_lista(html, numero_cnj)
            if not processo_encontrado:
                return None

            # 6. Busca detalhe completo
            detalhe_url = f"{base}/consultaPublica/consultaPublica.do"
            detalhe_params = {
                "actionMethod": "consultaPublica:consultaProcessoAction.展开Detail",
                "numeroProcesso": processo_encontrado,
                "conversationId": conversation_id,
            }
            if conversation_id:
                detalhe_url += f"?conversationId={conversation_id}"

            resp_detalhe = await self._post(detalhe_url, data=detalhe_params)
            return self._parse_detalhe(resp_detalhe.text, processo_encontrado, tribunal.upper())

        except Exception as e:
            logger.warning("Projudi %s: erro ao buscar %s — %s", tribunal.upper(), numero_cnj, e)
            return None

    async def buscar_por_oab(
        self,
        numero_oab: str,
        uf_oab: str,
        nome_advogado: str = None,
        **kwargs: Any,
    ) -> list[ProcessoCompleto]:
        """
        Busca processos de um advogado pela OAB no PROJUDI.

        O PROJUDI tem endpoint AJAX que retorna lista paginada.
        """
        processos = []
        base = PROJUDI_URLS.get(f"tj{uf_oab.lower()}")
        if not base:
            # Tenta tribunais que usam PROJUDI
            for t in ["tjpr", "tjgo", "tjmt", "tjam"]:
                if f"{uf_oab.upper()}" in t.upper():
                    base = PROJUDI_URLS.get(t)
                    break
        if not base:
            return processos

        try:
            oab_match = OAB_PATTERN.search(numero_oab.upper())
            if not oab_match:
                logger.warning("Projudi: OAB inválida %s", numero_oab)
                return processos

            numero_formatado = oab_match.group(1)
            uf_formatada = oab_match.group(2).upper()

            # Sessão inicial
            await self._get(f"{base}/consultaPublica/consultaPublica.do")

            # Busca por OAB
            search_url = f"{base}/consultaPublica/consultaPublica.do"
            params = {
                "actionMethod": "consultaPublica:consultaAdvogadoAction.buscarProcessos",
                "numeroOAB": numero_formatado,
                "ufOAB": uf_formatada,
                "conversationId": "",
            }

            resp = await self._post(search_url, data=params)
            html = resp.text

            # Extrai todos os números de processo da lista
            numeros = CNJ_PATTERN.findall(html)
            numeros = list(dict.fromkeys(numeros))

            logger.info("Projudi %s: encontrados %d processos para OAB %s/%s",
                        base.split(".")[-1].upper(), len(numeros), numero_formatado, uf_formatada)

            # Para cada processo, busca o detalhe
            for num in numeros[:50]:  # Limita a 50 para evitar spam
                proc = await self.buscar_processo(num, f"tj{uf_formatada.lower()}")
                if proc:
                    processos.append(proc)

        except Exception as e:
            logger.warning("Projudi: erro na busca por OAB %s/%s — %s", numero_oab, uf_oab, e)

        return processos

    def _extrair_numero_da_lista(self, html: str, numero_cnj: str) -> Optional[str]:
        """Extrai o número exato do processo da página de resultados."""
        soup = BeautifulSoup(html, "html.parser")
        # Procura links com número CNJ
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            texto = link.get_text(strip=True)
            if CNJ_PATTERN.match(texto.replace(".", "").replace("-", "")):
                return texto
            if numero_cnj.replace(".", "").replace("-", "") in texto.replace(".", "").replace("-", ""):
                return texto
        return numero_cnj  # Retorna o original se não encontrar

    def _parse_detalhe(self, html: str, numero_cnj: str, tribunal: str) -> ProcessoCompleto:
        """
        Parse do HTML de detalhe do PROJUDI.

        Estrutura típica:
        - Tabela #dadosBasicos com comarca, vara, classe
        - Tabela #partes com polos (ativo/passivo)
        - Tabela #movimentacoes com data, descrição
        """
        soup = BeautifulSoup(html, "html.parser")

        # ---- Dados básicos ----
        comarca = ""
        vara = ""
        classe = ""
        distribuicao = None
        valor = None
        situacao = ""

        # Procura tabela de dados básicos
        for tabela in soup.find_all("table", class_=re.compile(r"dados|basico", re.I)):
            for linha in tabela.find_all("tr"):
                colunas = linha.find_all(["td", "th"])
                if len(colunas) >= 2:
                    rotulo = colunas[0].get_text(strip=True).upper()
                    valor_col = colunas[1].get_text(strip=True)
                    if "COMARCA" in rotulo:
                        comarca = valor_col
                    elif "VARA" in rotulo or "ÓRGÃO" in rotulo:
                        vara = valor_col
                    elif "CLASSE" in rotulo:
                        classe = valor_col
                    elif "DISTRIBUIÇÃO" in rotulo or "DATA" in rotulo:
                        distribuicao = self._parse_data_brasileira(valor_col)
                    elif "VALOR" in rotulo:
                        valor = self._parse_valor(valor_col)
                    elif "SITUAÇÃO" in rotulo or "STATUS" in rotulo:
                        situacao = valor_col

        # ---- Partes ----
        partes: list[ParteProcesso] = []
        polo_atual = "OUTROS"
        for tabela in soup.find_all("table"):
            classes = tabela.get("class", [])
            if any("parte" in str(c).lower() for c in classes):
                for linha in tabela.find_all("tr"):
                    celulas = linha.find_all(["td", "th"])
                    if len(celulas) >= 2:
                        rotulo = celulas[0].get_text(strip=True).upper()
                        if "POLO" in rotulo or "ATIVO" in rotulo or "PASSIVO" in rotulo:
                            if "ATIVO" in rotulo:
                                polo_atual = "ATIVO"
                            elif "PASSIVO" in rotulo:
                                polo_atual = "PASSIVO"
                            continue
                        texto = celulas[0].get_text(strip=True)
                        if "ADVOGADO" in texto.upper():
                            nome_adv = celulas[1].get_text(strip=True) if len(celulas) > 1 else ""
                            oab_match = OAB_PATTERN.search(texto)
                            partes.append(ParteProcesso(
                                nome=nome_adv.upper(),
                                tipo_parte="ADVOGADO",
                                polo=polo_atual,
                                oab=oab_match.group(0) if oab_match else None,
                            ))
                        elif texto and len(texto) > 3:
                            tipo = "REQUERENTE" if polo_atual == "ATIVO" else "REQUERIDO"
                            if "RÉU" in texto.upper() or "REQUERIDO" in texto.upper():
                                tipo = "REQUERIDO"
                            elif "AUTOR" in texto.upper() or "REQUERENTE" in texto.upper():
                                tipo = "REQUERENTE"
                            partes.append(ParteProcesso(
                                nome=texto.upper(),
                                tipo_parte=tipo,
                                polo=polo_atual,
                            ))

        # ---- Movimentações ----
        movimentacoes: list[MovimentacaoProcesso] = []
        for tabela in soup.find_all("table"):
            classes = tabela.get("class", [])
            if any("moviment" in str(c).lower() for c in classes):
                for linha in tabela.find_all("tr"):
                    celulas = linha.find_all(["td", "th"])
                    if len(celulas) >= 2:
                        data_texto = celulas[0].get_text(strip=True)
                        desc_texto = " ".join(c.get_text(strip=True) for c in celulas[1:])
                        if data_texto and desc_texto:
                            data = self._parse_data_brasileira(data_texto)
                            if data:
                                movimentacoes.append(MovimentacaoProcesso(
                                    data_movimentacao=data,
                                    descricao=desc_texto,
                                    tipo="",
                                    impacto="",
                                ))

        return ProcessoCompleto(
            numero_cnj=numero_cnj,
            tribunal=tribunal,
            comarca=comarca,
            grau=self._inferir_grau(numero_cnj),
            vara=vara,
            classe_processual=classe,
            data_distribuicao=distribuicao,
            valor_causa=valor,
            situacao=situacao,
            partes=partes,
            movimentacoes=movimentacoes,
        )

    def _parse_data_brasileira(self, texto: str) -> Optional[datetime]:
        """Converte data no formato brasileiro DD/MM/YYYY ou DD/MM/YYYY HH:MM."""
        if not texto:
            return None
        texto = texto.strip()
        for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(texto[:len("DD/MM/YYYY")], fmt)
            except ValueError:
                pass
        return None

    def _parse_valor(self, texto: str) -> Optional[float]:
        """Converte valor monetário brasileiro R$ 1.234,56."""
        if not texto:
            return None
        texto = texto.replace("R$", "").replace("$", "").strip()
        texto = texto.replace(".", "").replace(",", ".")
        try:
            return float(texto)
        except ValueError:
            return None

    def _inferir_grau(self, numero_cnj: str) -> str:
        """Infere o grau do processo pelo número CNJ (G1, G2, RECURSAL)."""
        # CNJ: NNNNNNN-DD.YYYY.N.NN.NNNN — o 10º dígito indica o grau
        digits = re.sub(r"[^0-9]", "", numero_cnj)
        if len(digits) >= 10:
            grau_digit = digits[9]
            mapping = {"1": "G1", "2": "G2", "3": "RECURSAL"}
            return mapping.get(grau_digit, "G1")
        return "G1"
