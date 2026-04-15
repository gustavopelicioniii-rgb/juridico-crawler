"""
Testes para o crawler DataJud.
"""

import pytest
import httpx
from unittest.mock import AsyncMock, patch

from src.crawlers.datajud import DataJudCrawler, TRIBUNAL_ENDPOINT


class TestTribunalEndpoint:
    def test_tribunais_conhecidos_mapeados(self):
        assert "tjsp" in TRIBUNAL_ENDPOINT
        assert "stj" in TRIBUNAL_ENDPOINT
        assert "trf1" in TRIBUNAL_ENDPOINT
        assert "trt2" in TRIBUNAL_ENDPOINT

    def test_mais_de_80_tribunais(self):
        assert len(TRIBUNAL_ENDPOINT) >= 80

    def test_get_endpoint_tribunal_valido(self):
        crawler = DataJudCrawler.__new__(DataJudCrawler)
        crawler.rate_limiter = None
        crawler.max_retries = 3
        crawler.timeout = 30.0
        crawler._client = None

        from src.config import settings
        url = crawler._get_endpoint("tjsp")
        assert "api_publica_tjsp" in url
        assert settings.datajud_base_url in url

    def test_get_endpoint_tribunal_invalido(self):
        crawler = DataJudCrawler.__new__(DataJudCrawler)
        with pytest.raises(ValueError, match="não suportado"):
            crawler._get_endpoint("tribunal_invalido_xyz")

    def test_query_elasticsearch(self):
        crawler = DataJudCrawler.__new__(DataJudCrawler)
        numero = "0001234-56.2024.8.26.0001"
        query = crawler._montar_query(numero)
        assert query["query"]["match"]["numeroProcesso"] == numero
        assert query["size"] == 1


class TestDataJudCrawler:
    @pytest.fixture
    def resposta_datajud(self):
        """Fixture com resposta simulada do DataJud."""
        return {
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_source": {
                            "numeroProcesso": "0001234-56.2024.8.26.0001",
                            "tribunal": "TJSP",
                            "classe": {"nome": "Procedimento Comum Cível"},
                            "assuntos": [{"nome": "Cobrança"}],
                            "orgaoJulgador": {
                                "nome": "1ª Vara Cível de São Paulo",
                                "codigoMunicipioIBGE": "3550308",
                            },
                            "dataAjuizamento": "2024-01-15",
                            "nivelSigilo": 0,
                            "partes": [
                                {
                                    "nome": "JOÃO DA SILVA",
                                    "tipoParte": "AUTOR",
                                    "polo": "ATIVO",
                                    "advogados": [
                                        {
                                            "nome": "MARIA SOUZA",
                                            "numeroOAB": "123456",
                                            "ufOAB": "SP",
                                        }
                                    ],
                                },
                                {
                                    "nome": "EMPRESA XYZ LTDA",
                                    "tipoParte": "RÉU",
                                    "polo": "PASSIVO",
                                    "advogados": [],
                                },
                            ],
                            "movimentos": [
                                {
                                    "dataHora": "2024-06-01T10:00:00",
                                    "nome": "Sentença",
                                    "codigo": 22,
                                },
                                {
                                    "dataHora": "2024-01-15T09:00:00",
                                    "nome": "Distribuição",
                                    "codigo": 51,
                                },
                            ],
                        }
                    }
                ],
            }
        }

    @pytest.mark.asyncio
    async def test_buscar_processo_encontrado(self, resposta_datajud):
        """Testa parsing básico quando processo é encontrado."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.json.return_value = resposta_datajud
        mock_response.raise_for_status = AsyncMock()

        async with DataJudCrawler() as crawler:
            with patch.object(crawler, "_post", return_value=mock_response):
                resultado = await crawler.buscar_processo(
                    numero_cnj="0001234-56.2024.8.26.0001",
                    tribunal="tjsp",
                    usar_ai_parser=False,  # Sem AI para não precisar de API key
                )

        assert resultado is not None
        assert resultado.numero_cnj == "0001234-56.2024.8.26.0001"
        assert resultado.tribunal == "tjsp"
        assert len(resultado.partes) >= 2
        assert len(resultado.movimentacoes) == 2

    @pytest.mark.asyncio
    async def test_buscar_processo_nao_encontrado(self):
        """Testa retorno None quando processo não existe."""
        mock_response = AsyncMock(spec=httpx.Response)
        mock_response.json.return_value = {"hits": {"hits": []}}
        mock_response.raise_for_status = AsyncMock()

        async with DataJudCrawler() as crawler:
            with patch.object(crawler, "_post", return_value=mock_response):
                resultado = await crawler.buscar_processo(
                    numero_cnj="0000000-00.2000.0.00.0000",
                    tribunal="tjsp",
                    usar_ai_parser=False,
                )

        assert resultado is None

    @pytest.mark.asyncio
    async def test_parse_basico_partes(self, resposta_datajud):
        """Testa extração de partes no parse básico."""
        fonte = resposta_datajud["hits"]["hits"][0]["_source"]
        crawler = DataJudCrawler.__new__(DataJudCrawler)
        resultado = crawler._parse_basico(fonte, "tjsp")

        nomes = [p.nome for p in resultado.partes]
        tipos = [p.tipo_parte for p in resultado.partes]

        assert "MARIA SOUZA" in nomes  # Advogada
        assert "ADVOGADO" in tipos

    @pytest.mark.asyncio
    async def test_parse_basico_movimentacoes_ordenadas(self, resposta_datajud):
        """Testa que movimentações são ordenadas da mais recente para a mais antiga."""
        fonte = resposta_datajud["hits"]["hits"][0]["_source"]
        crawler = DataJudCrawler.__new__(DataJudCrawler)
        resultado = crawler._parse_basico(fonte, "tjsp")

        assert len(resultado.movimentacoes) == 2
        # Mais recente primeiro
        assert resultado.movimentacoes[0].data_movimentacao > resultado.movimentacoes[1].data_movimentacao
