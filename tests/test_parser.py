"""
Testes para o AI Parser (sem chamar a API real do Claude).
"""

import json
import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.parsers.ai_parser import _montar_processo_completo, extrair_dados_completos
from src.parsers.estruturas import ProcessoCompleto


class TestMontarProcessoCompleto:
    """Testa a função de montagem sem precisar da API Claude."""

    def _dados_validos(self) -> dict:
        return {
            "numero_cnj": "0001234-56.2024.8.26.0001",
            "tribunal": "TJSP",
            "vara": "1ª VARA CÍVEL",
            "comarca": "SÃO PAULO",
            "classe_processual": "PROCEDIMENTO COMUM CÍVEL",
            "assunto": "COBRANÇA",
            "valor_causa": "15000.50",
            "data_distribuicao": "2024-01-15",
            "situacao": "EM ANDAMENTO",
            "segredo_justica": False,
            "partes": [
                {
                    "nome": "JOÃO DA SILVA",
                    "tipo_parte": "AUTOR",
                    "polo": "ATIVO",
                    "documento": "12345678901",
                    "oab": None,
                },
                {
                    "nome": "MARIA SOUZA ADVOCACIA",
                    "tipo_parte": "ADVOGADO",
                    "polo": "ATIVO",
                    "documento": None,
                    "oab": "123456SP",
                },
                {
                    "nome": "EMPRESA XYZ LTDA",
                    "tipo_parte": "RÉU",
                    "polo": "PASSIVO",
                    "documento": "12345678000190",
                    "oab": None,
                },
            ],
            "movimentacoes": [
                {
                    "data_movimentacao": "2024-06-01",
                    "descricao": "Sentença de procedência",
                    "tipo": "SENTENÇA",
                    "complemento": None,
                    "codigo_nacional": 22,
                },
                {
                    "data_movimentacao": "2024-01-15",
                    "descricao": "Distribuição por dependência",
                    "tipo": None,
                    "complemento": None,
                    "codigo_nacional": 51,
                },
            ],
        }

    def test_numero_cnj_mapeado(self):
        dados = self._dados_validos()
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert resultado.numero_cnj == "0001234-56.2024.8.26.0001"

    def test_valor_causa_decimal(self):
        dados = self._dados_validos()
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert resultado.valor_causa == Decimal("15000.50")

    def test_data_distribuicao_parseada(self):
        dados = self._dados_validos()
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert resultado.data_distribuicao == date(2024, 1, 15)

    def test_partes_extraidas(self):
        dados = self._dados_validos()
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert len(resultado.partes) == 3
        nomes = [p.nome for p in resultado.partes]
        assert "JOÃO DA SILVA" in nomes
        assert "MARIA SOUZA ADVOCACIA" in nomes

    def test_oab_extraida(self):
        dados = self._dados_validos()
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        adv = next(p for p in resultado.partes if p.tipo_parte == "ADVOGADO")
        assert adv.oab == "123456SP"

    def test_movimentacoes_ordenadas(self):
        dados = self._dados_validos()
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert len(resultado.movimentacoes) == 2
        assert resultado.movimentacoes[0].data_movimentacao > resultado.movimentacoes[1].data_movimentacao

    def test_movimentacao_codigo_nacional(self):
        dados = self._dados_validos()
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        sentenca = next(m for m in resultado.movimentacoes if m.tipo == "SENTENÇA")
        assert sentenca.codigo_nacional == 22

    def test_parte_sem_nome_ignorada(self):
        dados = self._dados_validos()
        dados["partes"].append({"nome": "", "tipo_parte": "OUTRO", "polo": None})
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert len(resultado.partes) == 3  # Ignora a parte sem nome

    def test_movimentacao_data_invalida_ignorada(self):
        dados = self._dados_validos()
        dados["movimentacoes"].append({
            "data_movimentacao": "data-invalida",
            "descricao": "Teste",
        })
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert len(resultado.movimentacoes) == 2  # Ignora a data inválida

    def test_valor_causa_nulo(self):
        dados = self._dados_validos()
        dados["valor_causa"] = None
        resultado = _montar_processo_completo(dados, {}, "tjsp")
        assert resultado.valor_causa is None

    def test_dados_brutos_preservados(self):
        dados = self._dados_validos()
        brutos = {"original": "data"}
        resultado = _montar_processo_completo(dados, brutos, "tjsp")
        assert resultado.dados_brutos == brutos


class TestExtrairDadosCompletos:
    """Testa a função principal com mock do cliente Claude."""

    @pytest.mark.asyncio
    async def test_extrai_com_resposta_valida(self):
        resposta_claude = {
            "numero_cnj": "0001234-56.2024.8.26.0001",
            "tribunal": "TJSP",
            "vara": "1ª VARA",
            "comarca": "SÃO PAULO",
            "classe_processual": "PROCEDIMENTO COMUM CÍVEL",
            "assunto": "COBRANÇA",
            "valor_causa": "5000.00",
            "data_distribuicao": "2024-03-01",
            "situacao": "ATIVO",
            "segredo_justica": False,
            "partes": [
                {"nome": "TESTE AUTOR", "tipo_parte": "AUTOR", "polo": "ATIVO"}
            ],
            "movimentacoes": [
                {"data_movimentacao": "2024-03-01", "descricao": "Distribuição"}
            ],
        }

        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(resposta_claude))]

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_message

        with patch("src.parsers.ai_parser._get_client", return_value=mock_client):
            resultado = await extrair_dados_completos({"raw": "data"}, tribunal="tjsp")

        assert isinstance(resultado, ProcessoCompleto)
        assert resultado.numero_cnj == "0001234-56.2024.8.26.0001"
        assert len(resultado.partes) == 1

    @pytest.mark.asyncio
    async def test_falha_sem_api_key(self):
        with patch("src.parsers.ai_parser.settings") as mock_settings:
            mock_settings.anthropic_api_key = ""
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                await extrair_dados_completos({})
