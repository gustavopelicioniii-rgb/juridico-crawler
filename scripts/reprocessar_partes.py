"""
Reprocessa partes de processos que já estão no banco mas com partes = 0.
Usa dados_brutos (JSON do DataJud) já persistido — sem novo crawling.

Uso:
    python scripts/reprocessar_partes.py
    python scripts/reprocessar_partes.py --dry-run   # só mostra, não salva
    python scripts/reprocessar_partes.py --limite 50  # processa no máximo 50
"""

import asyncio
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession


async def reprocessar(dry_run: bool = False, limite: int = 0) -> None:
    # Imports tardios para não falhar se executado fora do contexto da API
    from src.database.connection import AsyncSessionLocal
    from src.database.models import Processo, Parte
    from src.parsers.ai_parser import extrair_partes_do_datajud

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Reprocessando partes...\n")

    async with AsyncSessionLocal() as db:
        # Buscar processos sem partes (independente de dados_brutos)
        stmt = (
            select(Processo)
            .outerjoin(Parte, Parte.processo_id == Processo.id)
            .group_by(Processo.id)
            .having(func.count(Parte.id) == 0)
            .order_by(Processo.id)
        )
        if limite > 0:
            stmt = stmt.limit(limite)

        result = await db.execute(stmt)
        processos = result.scalars().all()

        total = len(processos)
        sem_brutos = sum(1 for p in processos if not p.dados_brutos)
        com_brutos = total - sem_brutos

        print(f"Processos com 0 partes: {total}")
        print(f"  → Com dados_brutos (reprocessáveis) : {com_brutos}")
        print(f"  → Sem dados_brutos (precisam re-crawl): {sem_brutos}\n")

        if com_brutos == 0:
            print("Nenhum processo reprocessável via dados_brutos.")
            print("Os processos vieram do TJSP eSaj e precisam ser minerados novamente via /oab/minerar.")
            return

        reprocessados = 0
        partes_inseridas = 0
        erros = 0

        for proc in processos:
            if not proc.dados_brutos:
                print(f"  ⚠  {proc.numero_cnj}: sem dados_brutos — requer re-crawl")
                continue

            try:
                partes = extrair_partes_do_datajud(proc.dados_brutos)

                if not partes:
                    print(f"  ⚠  {proc.numero_cnj}: dados_brutos não tem partes")
                    continue

                print(f"  ✅ {proc.numero_cnj}: {len(partes)} parte(s) encontrada(s)")

                if not dry_run:
                    for p in partes:
                        db.add(Parte(
                            processo_id=proc.id,
                            tipo_parte=p.tipo_parte,
                            nome=p.nome,
                            documento=p.documento,
                            oab=p.oab,
                            polo=p.polo,
                        ))

                reprocessados += 1
                partes_inseridas += len(partes)

            except Exception as e:
                print(f"  ❌ {proc.numero_cnj}: erro — {e}")
                erros += 1

        if not dry_run and partes_inseridas > 0:
            await db.commit()

    print(f"\n{'─' * 50}")
    print(f"Reprocessados : {reprocessados}/{total}")
    print(f"Partes {'(simuladas)' if dry_run else 'inseridas'}: {partes_inseridas}")
    print(f"Erros         : {erros}")
    if dry_run:
        print("\n[DRY RUN] Nada foi salvo. Rode sem --dry-run para aplicar.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reprocessa partes de processos sem partes")
    parser.add_argument("--dry-run", action="store_true", help="Simula sem salvar")
    parser.add_argument("--limite", type=int, default=0, help="Máximo de processos (0 = todos)")
    args = parser.parse_args()

    asyncio.run(reprocessar(dry_run=args.dry_run, limite=args.limite))
