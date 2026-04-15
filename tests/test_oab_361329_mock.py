"""
Dry-run do pipeline de extração com JSONs simulados baseados na estrutura real
retornada pelo DataJud CNJ para processos do TJSP.

Não faz requisições HTTP — valida que _parse_basico extrai corretamente:
  - partes (com polos ATIVO/PASSIVO, tipos e advogados com OAB)
  - valor_causa (em vários formatos: int, float, string com R$)
  - segredo_justica (nivelSigilo > 0 ou situação com "segredo")
  - observacoes (populado automaticamente)

Executar:
    python -m pytest tests/test_oab_361329_mock.py -v
    # ou standalone:
    python tests/test_oab_361329_mock.py
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.crawlers.datajud import DataJudCrawler


# ============================================================
# Fixtures: JSONs baseados na estrutura real do DataJud CNJ
# Estrutura documentada em: https://datajud-wiki.cnj.jus.br/api-publica/
# ============================================================

PROCESSO_PUBLICO_COM_OAB = {
    "numeroProcesso": "1000123-45.2024.8.26.0100",
    "classe": {"codigo": 436, "nome": "Procedimento Comum Cível"},
    "assuntos": [{"codigo": 10375, "nome": "Indenização por Dano Moral"}],
    "valorCausa": 50000.00,
    "nivelSigilo": 0,
    "dataAjuizamento": "2024-03-15T10:30:00.000Z",
    "grau": "G1",
    "orgaoJulgador": {
        "codigo": 1234,
        "nome": "1ª Vara Cível do Foro Central",
        "codigoMunicipioIBGE": 3550308,
    },
    "partes": [
        {
            "tipoParte": "REQUERENTE",
            "nome": "José da Silva",
            "cpf": "123.456.789-00",
            "advogados": [
                {
                    "nome": "Dr. Advogado Teste",
                    "numeroOAB": "361329",
                    "ufOAB": "SP",
                }
            ],
        },
        {
            "tipoParte": "REQUERIDO",
            "nome": "Empresa Ré LTDA",
            "cnpj": "12.345.678/0001-90",
            "advogados": [
                {
                    "nome": "Dra. Advogada Adversária",
                    "numeroOAB": "999999",
                    "ufOAB": "SP",
                }
            ],
        },
    ],
    "movimentos": [
        {"dataHora": "2024-03-15T10:30:00.000Z", "nome": "Distribuído por Sorteio", "codigo": 26},
        {"dataHora": "2024-04-01T15:00:00.000Z", "nome": "Citação Realizada", "codigo": 51},
    ],
}

PROCESSO_VALOR_STRING_BR = {
    "numeroProcesso": "2000456-78.2024.8.26.0100",
    "classe": {"nome": "Execução de Título Extrajudicial"},
    "assuntos": [{"nome": "Contrato Bancário"}],
    "valorCausa": "R$ 125.000,50",  # formato brasileiro com R$ e vírgula decimal
    "nivelSigilo": 0,
    "dataAjuizamento": "2024-05-20",
    "orgaoJulgador": {"nome": "2ª Vara Cível", "municipio": "São Paulo"},
    "partes": [
        {
            "tipoParte": "EXEQUENTE",
            "nome": "Banco XYZ S.A.",
            "advogados": [{"nome": "Adv Banco", "numeroOAB": "0361329", "ufOAB": "SP"}],
        },
        {"tipoParte": "EXECUTADO", "nome": "Devedor Fulano"},
    ],
    "movimentos": [],
}

PROCESSO_EM_SEGREDO = {
    "numeroProcesso": "3000789-01.2024.8.26.0100",
    "classe": {"nome": "Ação de Divórcio Litigioso"},
    "assuntos": [{"nome": "Dissolução"}],
    "valorCausa": None,  # típico em segredo
    "nivelSigilo": 3,  # segredo de justiça nível 3
    "dataAjuizamento": "2024-06-10",
    "orgaoJulgador": {"nome": "Vara de Família"},
    "partes": [
        {
            "tipoParte": "REQUERENTE",
            "nome": "J. S.",  # nome ocultado pelo tribunal
            "advogados": [{"nome": "Dr. Advogado", "numeroOAB": "361329", "ufOAB": "SP"}],
        }
    ],
    "movimentos": [],
}

PROCESSO_SEM_VALOR = {
    "numeroProcesso": "4000111-22.2024.5.02.0001",  # formato trabalhista
    "classe": {"nome": "Reclamação Trabalhista"},
    "assuntos": [{"nome": "Verbas Rescisórias"}],
    "nivelSigilo": 0,
    "dataAjuizamento": "2024-07-01",
    "orgaoJulgador": {"nome": "1ª Vara do Trabalho de São Paulo"},
    "partes": [
        {
            "tipoParte": "RECLAMANTE",
            "nome": "Trabalhador Exemplo",
            "advogados": [{"nome": "Adv Trabalhista", "numeroOAB": "361329", "ufOAB": "SP"}],
        },
        {"tipoParte": "RECLAMADO", "nome": "Empregador LTDA"},
    ],
    "movimentos": [],
}


# ============================================================
# Asserts
# ============================================================

def test_processo_publico_com_oab():
    crawler = DataJudCrawler()
    p = crawler._parse_basico(PROCESSO_PUBLICO_COM_OAB, "tjsp")

    assert p.numero_cnj == "1000123-45.2024.8.26.0100"
    assert p.tribunal == "tjsp"
    assert p.segredo_justica is False
    assert p.valor_causa == Decimal("50000.00")
    assert p.observacoes is None, f"esperava sem observações, veio: {p.observacoes}"

    # Partes: 2 + 2 advogados = 4
    assert len(p.partes) == 4, f"esperava 4 partes, veio {len(p.partes)}"

    nomes = {pt.nome for pt in p.partes}
    assert "JOSÉ DA SILVA" in nomes
    assert "EMPRESA RÉ LTDA" in nomes
    assert "DR. ADVOGADO TESTE" in nomes

    # Polos
    ativos = [pt for pt in p.partes if pt.polo == "ATIVO"]
    passivos = [pt for pt in p.partes if pt.polo == "PASSIVO"]
    assert len(ativos) == 2  # REQUERENTE + seu advogado
    assert len(passivos) == 2  # REQUERIDO + seu advogado

    # OAB formatada
    adv_alvo = next(pt for pt in p.partes if pt.nome == "DR. ADVOGADO TESTE")
    assert adv_alvo.oab == "361329/SP"
    assert adv_alvo.tipo_parte == "ADVOGADO"

    print("✓ test_processo_publico_com_oab")


def test_valor_causa_formato_brasileiro():
    crawler = DataJudCrawler()
    p = crawler._parse_basico(PROCESSO_VALOR_STRING_BR, "tjsp")

    assert p.valor_causa == Decimal("125000.50"), f"veio {p.valor_causa}"
    assert p.segredo_justica is False

    # Duas partes, uma com advogado OAB 0361329
    advs = [pt for pt in p.partes if pt.tipo_parte == "ADVOGADO"]
    assert len(advs) == 1
    assert advs[0].oab == "0361329/SP"

    print("✓ test_valor_causa_formato_brasileiro (R$ 125.000,50 → 125000.50)")


def test_segredo_de_justica():
    crawler = DataJudCrawler()
    p = crawler._parse_basico(PROCESSO_EM_SEGREDO, "tjsp")

    assert p.segredo_justica is True
    assert p.situacao == "Segredo de Justiça"
    assert p.observacoes is not None
    assert "SEGREDO DE JUSTIÇA" in p.observacoes.upper()
    assert "nível 3" in p.observacoes

    # Valor da causa ausente: deve registrar na observação
    assert "valor da causa" in p.observacoes.lower()

    print("✓ test_segredo_de_justica")
    print(f"   observações: {p.observacoes}")


def test_processo_sem_valor_registra_observacao():
    crawler = DataJudCrawler()
    p = crawler._parse_basico(PROCESSO_SEM_VALOR, "tjsp")

    assert p.valor_causa is None
    assert p.segredo_justica is False
    assert p.observacoes is not None
    assert "valor da causa" in p.observacoes.lower()
    assert "complementar" in p.observacoes.lower()

    print("✓ test_processo_sem_valor_registra_observacao")


def test_pipeline_completo_oab_361329():
    """Simula o pipeline completo buscando 4 processos fictícios e verificando saída."""
    crawler = DataJudCrawler()
    fontes = [
        PROCESSO_PUBLICO_COM_OAB,
        PROCESSO_VALOR_STRING_BR,
        PROCESSO_EM_SEGREDO,
        PROCESSO_SEM_VALOR,
    ]
    processos = [crawler._parse_basico(f, "tjsp") for f in fontes]

    # Estatísticas esperadas
    total = len(processos)
    com_partes = sum(1 for p in processos if p.partes)
    com_valor = sum(1 for p in processos if p.valor_causa is not None)
    em_segredo = sum(1 for p in processos if p.segredo_justica)

    assert total == 4
    assert com_partes == 4, f"esperava 4 com partes, veio {com_partes}"
    assert com_valor == 2, f"esperava 2 com valor, veio {com_valor}"
    assert em_segredo == 1, f"esperava 1 em segredo, veio {em_segredo}"

    print()
    print("=" * 60)
    print(f"PIPELINE OAB 361329/SP — dry-run")
    print("=" * 60)
    print(f"Total processos:       {total}")
    print(f"  com partes:          {com_partes}/{total}")
    print(f"  com valor da causa:  {com_valor}/{total}")
    print(f"  em segredo:          {em_segredo}/{total}")
    print()
    for p in processos:
        flag = "🔒" if p.segredo_justica else "  "
        valor = f"R$ {p.valor_causa:,.2f}" if p.valor_causa else "—"
        advs = [pt.oab for pt in p.partes if pt.tipo_parte == "ADVOGADO"]
        print(f"{flag} {p.numero_cnj}")
        print(f"    valor: {valor}  |  advs: {advs}")
        print(f"    partes: {len(p.partes)}  |  obs: {p.observacoes or '—'}")
        print()


if __name__ == "__main__":
    test_processo_publico_com_oab()
    test_valor_causa_formato_brasileiro()
    test_segredo_de_justica()
    test_processo_sem_valor_registra_observacao()
    test_pipeline_completo_oab_361329()
    print("\n✅ Todos os testes passaram!")
