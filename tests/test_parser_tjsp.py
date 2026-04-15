"""
Testa o parser de partes do TJSP usando arquivos HTML salvos localmente.
Roda sem precisar de rede — usa os HTMLs capturados pelo debug_processo.py.

Uso:
    python tests/test_parser_tjsp.py
    # ou via pytest:
    pytest tests/test_parser_tjsp.py -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.crawlers.tjsp import TJSPCrawler  # noqa: E402
from src.parsers.estruturas import ParteProcesso  # noqa: E402

# Cria instância sem inicializar httpx (não precisamos de rede aqui)
crawler = TJSPCrawler.__new__(TJSPCrawler)
crawler.tribunal_id = "tjsp"


def _parsear_html(html: str) -> list[ParteProcesso]:
    """Roda o mesmo fluxo de extração de partes do _parsear_detalhe."""
    try:
        from selectolax.parser import HTMLParser
    except ImportError:
        raise RuntimeError("Instale selectolax: pip install selectolax")

    tree = HTMLParser(html)
    partes: list[ParteProcesso] = []

    parties_table = (
        tree.css_first("#tablePartesPrincipais")
        or tree.css_first("#tableTodasPartes")
        or tree.css_first("table[id*='Partes']")
    )

    if parties_table:
        current_tipo = None
        for row in parties_table.css("tr"):
            label_td = row.css_first("td.label")
            if not label_td:
                for td in row.css("td"):
                    t = td.text(strip=True)
                    if t.endswith(":") and len(t) < 60 and "\n" not in t:
                        label_td = td
                        break
            if label_td:
                raw_label = re.sub(r"[\s\xa0\u00a0]+", " ", label_td.text()).strip().rstrip(":")
                if raw_label:
                    current_tipo = raw_label.upper()
            for node in row.css("td.nomeParteEAdvogado, span.nomeParteEAdvogado"):
                polo = crawler._polo_de_tipo(current_tipo or "")
                partes.extend(crawler._extrair_partes_de_node(node, polo, current_tipo))

    # Fallback A
    if not partes:
        current_tipo_fb = None
        for row in tree.css("tr"):
            nos = row.css("td.nomeParteEAdvogado, span.nomeParteEAdvogado")
            if not nos:
                continue
            cells = row.css("td")
            if cells:
                primeiro_td = re.sub(r"[\s\xa0\u00a0]+", " ", cells[0].text()).strip()
                if primeiro_td and len(primeiro_td) < 60:
                    current_tipo_fb = primeiro_td.rstrip(":").strip().upper() or current_tipo_fb
            for node in nos:
                polo = crawler._polo_de_tipo(current_tipo_fb or "")
                partes.extend(crawler._extrair_partes_de_node(node, polo, current_tipo_fb))

    return partes


DEBUG_DIR = ROOT / "tests"


def test_1006882_partes_extraidas():
    """Processo com td.nomeParteEAdvogado — era 0 partes antes da correção."""
    html_file = DEBUG_DIR / "debug_1006882_45_2022_8_26_0048.html"
    if not html_file.exists():
        print(f"SKIP: {html_file} não encontrado (rode debug_processo.py primeiro)")
        return

    html = html_file.read_text(encoding="utf-8")
    partes = _parsear_html(html)

    nomes = [p.nome for p in partes]
    tipos = [p.tipo_parte for p in partes]

    assert len(partes) >= 3, f"Esperava >= 3 partes, obteve {len(partes)}: {nomes}"
    assert "VALDEMIR POLONI" in nomes, f"Parte principal não encontrada: {nomes}"
    assert "SOLANGE SILVA BRAZ" in nomes, f"Advogada não encontrada: {nomes}"
    assert "ADVOGADO" in tipos, f"Tipo ADVOGADO não encontrado: {tipos}"

    # Polo correto
    polo_reqte = next((p.polo for p in partes if p.nome == "VALDEMIR POLONI"), None)
    assert polo_reqte == "ATIVO", f"Polo do requerente errado: {polo_reqte}"

    polo_reqda = next((p.polo for p in partes if "HELENA" in p.nome), None)
    assert polo_reqda == "PASSIVO", f"Polo da requerida errado: {polo_reqda}"

    print(f"OK: {len(partes)} partes extraídas de 1006882")
    for p in partes:
        print(f"  [{p.polo:8}] [{p.tipo_parte}] {p.nome}")


def test_1002201_partes_extraidas():
    """Processo com requerente e dois advogados — era 0 partes antes."""
    html_file = DEBUG_DIR / "debug_1002201_27_2025_8_26_0048.html"
    if not html_file.exists():
        print(f"SKIP: {html_file} não encontrado")
        return

    html = html_file.read_text(encoding="utf-8")
    partes = _parsear_html(html)

    nomes = [p.nome for p in partes]
    assert len(partes) >= 3, f"Esperava >= 3 partes, obteve {len(partes)}: {nomes}"
    assert any("ADVOGADO" == p.tipo_parte for p in partes), "Advogado não extraído"

    advs = [p for p in partes if p.tipo_parte == "ADVOGADO"]
    assert len(advs) >= 2, f"Esperava >= 2 advogados, obteve {len(advs)}"

    print(f"OK: {len(partes)} partes extraídas de 1002201")
    for p in partes:
        print(f"  [{p.polo:8}] [{p.tipo_parte}] {p.nome}")


def test_0027984_processo_criminal():
    """Processo criminal com Justiça Pública como autor."""
    html_file = DEBUG_DIR / "debug_0027984_37_2022_8_26_0050.html"
    if not html_file.exists():
        print(f"SKIP: {html_file} não encontrado")
        return

    html = html_file.read_text(encoding="utf-8")
    partes = _parsear_html(html)

    nomes = [p.nome for p in partes]
    assert "JUSTIÇA PÚBLICA" in nomes, f"Autor não encontrado: {nomes}"

    polo_autor = next((p.polo for p in partes if p.nome == "JUSTIÇA PÚBLICA"), None)
    assert polo_autor == "ATIVO", f"Polo do autor errado: {polo_autor}"

    print(f"OK: {len(partes)} partes extraídas de 0027984")
    for p in partes:
        print(f"  [{p.polo:8}] [{p.tipo_parte}] {p.nome}")


def test_polo_de_tipo():
    """Testa mapeamento de abreviações TJSP para polo."""
    assert crawler._polo_de_tipo("REQTE") == "ATIVO"
    assert crawler._polo_de_tipo("REQDA") == "PASSIVO"
    assert crawler._polo_de_tipo("REQDO") == "PASSIVO"
    assert crawler._polo_de_tipo("AUTOR") == "ATIVO"
    assert crawler._polo_de_tipo("RÉU") == "PASSIVO"
    assert crawler._polo_de_tipo("APELANTE") == "ATIVO"
    assert crawler._polo_de_tipo("APELADO") == "PASSIVO"
    assert crawler._polo_de_tipo("INTERESDO.") == "PASSIVO"
    print("OK: _polo_de_tipo mapeamentos corretos")


if __name__ == "__main__":
    print("=" * 60)
    print("Testando parser TJSP (sem rede)")
    print("=" * 60)
    test_polo_de_tipo()
    test_1006882_partes_extraidas()
    test_1002201_partes_extraidas()
    test_0027984_processo_criminal()
    print()
    print("Todos os testes passaram!")
