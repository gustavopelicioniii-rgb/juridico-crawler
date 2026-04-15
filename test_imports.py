#!/usr/bin/env python3
"""
Quick test para verificar se todos os imports funcionam.
Execute com: python test_imports.py
"""

import sys

print("🔍 Verificando imports...")

try:
    print("  ✓ src.config")
    from src.config import settings

    print("  ✓ src.database.models")
    from src.database.models import (
        Processo, Parte, Movimentacao, Monitoramento,
        Notificacao, Prazo, Base
    )

    print("  ✓ src.database.connection")
    from src.database.connection import AsyncSessionLocal, engine

    print("  ✓ src.api.auth")
    from src.api.auth import verificar_api_key

    print("  ✓ src.api.schemas")
    from src.api.schemas import ProcessoSchema, ParteSchema

    print("  ✓ src.api.routes.processos")
    from src.api.routes import processos

    print("  ✓ src.api.routes.partes")
    from src.api.routes import partes

    print("  ✓ src.api.routes.monitoramento")
    from src.api.routes import monitoramento

    print("  ✓ src.api.routes.notificacoes")
    from src.api.routes import notificacoes

    print("  ✓ src.api.routes.prazos")
    from src.api.routes import prazos

    print("  ✓ src.api.routes.oab")
    from src.api.routes import oab

    print("  ✓ src.crawlers.datajud")
    from src.crawlers.datajud import DataJudCrawler

    print("  ✓ src.scheduler.jobs")
    from src.scheduler.jobs import criar_scheduler

    print("  ✓ src.main")
    from src.main import app

    print(f"\n✅ Todos imports OK! App carregada com {len(app.routes)} rotas:\n")

    for route in sorted(app.routes, key=lambda r: str(r.path)):
        if hasattr(route, 'methods'):
            methods = ', '.join(sorted(route.methods or []))
            print(f"   {methods:20} {route.path}")

    print("\n🚀 Crawler está pronto para usar!")
    print("\nPróximos passos:")
    print("  1. Rode a migration: psql -f src/database/migrations/002_melhorias_advocacia.sql")
    print("  2. Configure API_SECRET_KEY no .env")
    print("  3. Inicie: uvicorn src.main:app --reload")

except Exception as e:
    print(f"\n❌ Erro: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
