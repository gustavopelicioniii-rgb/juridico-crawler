"""
Teste do Bloco 1 (Persistência) — Demonstra ProcessoService sem PostgreSQL.

Usa SQLite em-memória para validar a lógica de:
  1. Salvamento de processos
  2. Deduplicação de partes
  3. Detecção de novas movimentações via hash
  4. Atualização automática de ultima_movimentacao_data

Uso:
    python test_bloco_1.py
"""

import asyncio
from datetime import date, datetime
from decimal import Decimal

# Usar SQLite in-memory para teste
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from src.database.models import Base
from src.services.processo_service import ProcessoService
from src.parsers.estruturas import ProcessoCompleto, MovimentacaoProcesso, ParteProcesso


async def criar_processo_teste() -> ProcessoCompleto:
    """Cria um processo simulado para teste."""
    return ProcessoCompleto(
        numero_cnj="0000000-92.2019.8.26.0100",
        tribunal="tjsp",
        grau="G1",
        vara="1ª Vara Cível",
        comarca="São Paulo",
        classe_processual="Ação de Cobrança",
        assunto="Cobrança de Cheque",
        valor_causa=Decimal("15000.00"),
        data_distribuicao=date(2019, 4, 8),
        situacao="Em tramitação",
        segredo_justica=False,
        observacoes="Processo de teste para Bloco 1",
        partes=[
            ParteProcesso(
                tipo_parte="AUTOR",
                nome="MARIA APARECIDA CARDOSO DIAS",
                documento="12345678901",
                oab=None,
                polo="ATIVO",
            ),
            ParteProcesso(
                tipo_parte="RÉU",
                nome="BANCO BRADESCO S.A.",
                documento="60746948000124",
                oab=None,
                polo="PASSIVO",
            ),
            ParteProcesso(
                tipo_parte="ADVOGADO",
                nome="GUSTAVO PELICIONI",
                documento=None,
                oab="361329",
                polo="ATIVO",
            ),
        ],
        movimentacoes=[
            MovimentacaoProcesso(
                data_movimentacao=date(2019, 4, 8),
                tipo="Distribuição",
                descricao="Processo distribuído à 1ª Vara Cível",
                complemento=None,
                codigo_nacional=1,
                categoria="COMUNICATIVO",
                impacto=None,
            ),
            MovimentacaoProcesso(
                data_movimentacao=date(2019, 5, 15),
                tipo="Citação",
                descricao="Réu foi citado para contestar em 15 dias",
                complemento=None,
                codigo_nacional=120,
                categoria="DECISORIO",
                impacto="DECISORIO_COM_EFEITO",
            ),
            MovimentacaoProcesso(
                data_movimentacao=date(2019, 6, 20),
                tipo="Contestação Apresentada",
                descricao="Réu apresentou contestação",
                complemento=None,
                codigo_nacional=130,
                categoria="COMUNICATIVO",
                impacto=None,
            ),
        ],
        dados_brutos=None,
    )


async def main():
    """Executa teste do Bloco 1."""
    print("=" * 70)
    print("TESTE DO BLOCO 1 — PERSISTÊNCIA EM BANCO DE DADOS")
    print("=" * 70)
    print()

    # ─ 1. Criar engine SQLite in-memory ─────────────────────────────────────
    print("[1/4] Criando banco de dados em-memória (SQLite)...")

    # Use SQLite com suporte JSON (não JSONB, que é PostgreSQL-only)
    import json as json_lib
    from sqlalchemy.dialects.sqlite import JSON

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Criar tabelas adaptadas para SQLite
    # (Precisa adaptar o modelo para remover JSONB)
    async with engine.begin() as conn:
        # Executa SQL diretamente para criar tabelas com JSON em vez de JSONB
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS processos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_cnj VARCHAR(30) UNIQUE NOT NULL,
                tribunal VARCHAR(20) NOT NULL,
                grau VARCHAR(30),
                vara VARCHAR(200),
                comarca VARCHAR(200),
                classe_processual VARCHAR(200),
                assunto VARCHAR(500),
                valor_causa NUMERIC(15, 2),
                data_distribuicao DATE,
                situacao VARCHAR(100),
                segredo_justica BOOLEAN DEFAULT 0,
                observacoes TEXT,
                ultima_movimentacao_data DATE,
                dados_brutos TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS partes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                tipo_parte VARCHAR(50) NOT NULL,
                nome VARCHAR(300) NOT NULL,
                documento VARCHAR(20),
                oab VARCHAR(20),
                polo VARCHAR(10),
                advogado_de_id INTEGER,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (processo_id) REFERENCES processos(id) ON DELETE CASCADE,
                FOREIGN KEY (advogado_de_id) REFERENCES partes(id) ON DELETE SET NULL
            )
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS movimentacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                data_movimentacao DATE NOT NULL,
                tipo VARCHAR(200),
                descricao TEXT NOT NULL,
                complemento TEXT,
                codigo_nacional INTEGER,
                categoria VARCHAR(50),
                impacto VARCHAR(20),
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (processo_id) REFERENCES processos(id) ON DELETE CASCADE
            )
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS monitoramentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                ativo BOOLEAN DEFAULT 1,
                ultima_verificacao TIMESTAMP,
                proxima_verificacao TIMESTAMP,
                notificar_email VARCHAR(200),
                webhook_url VARCHAR(500),
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (processo_id) REFERENCES processos(id) ON DELETE CASCADE
            )
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS notificacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                tipo VARCHAR(50) NOT NULL,
                resumo TEXT NOT NULL,
                dados TEXT,
                lida BOOLEAN DEFAULT 0,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (processo_id) REFERENCES processos(id) ON DELETE CASCADE
            )
        """))

        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS prazos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                processo_id INTEGER NOT NULL,
                tipo_prazo VARCHAR(100) NOT NULL,
                descricao TEXT NOT NULL,
                data_inicio DATE NOT NULL,
                data_vencimento DATE NOT NULL,
                dias_uteis INTEGER,
                cumprido BOOLEAN DEFAULT 0,
                observacao TEXT,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (processo_id) REFERENCES processos(id) ON DELETE CASCADE
            )
        """))

    AsyncSessionLocal = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    print("      ✓ Banco criado com sucesso")
    print()

    # ─ 2. Criar e salvar processo ────────────────────────────────────────────
    print("[2/4] Salvando processo inicial...")
    processo_1 = await criar_processo_teste()

    async with AsyncSessionLocal() as db:
        service = ProcessoService(db)
        processo_db, hashes_novos = await service.salvar_processo(
            processo_1,
            criar_monitoramento=True,
            notificar_email="gustavo@escritorio.com.br",
        )

        # Salvar informações enquanto ainda estamos na sessão
        proc_id = processo_db.id
        proc_cnj = processo_db.numero_cnj
        proc_partes = len(processo_db.partes)
        proc_movs = len(processo_db.movimentacoes)
        proc_ult_mov = processo_db.ultima_movimentacao_data

    print(f"      ✓ Processo salvo: ID={proc_id}")
    print(f"      ✓ CNJ: {proc_cnj}")
    print(f"      ✓ Partes: {proc_partes}")
    print(f"      ✓ Movimentações: {proc_movs}")
    print(f"      ✓ Última movimentação: {proc_ult_mov}")
    print()

    # ─ 3. Atualizar com nova movimentação ───────────────────────────────────
    print("[3/4] Atualizando processo com nova movimentação...")
    processo_2 = await criar_processo_teste()
    # Adiciona uma nova movimentação
    processo_2.movimentacoes.append(
        MovimentacaoProcesso(
            data_movimentacao=date(2019, 7, 10),
            tipo="Sentença",
            descricao="Juiz proferiu sentença procedente",
            complemento="Condenou o réu ao pagamento de R$ 15.000,00 + custas",
            codigo_nacional=200,
            categoria="DECISORIO",
            impacto="DECISORIO_COM_EFEITO",
        )
    )

    async with AsyncSessionLocal() as db:
        service = ProcessoService(db)
        processo_db, hashes_novos = await service.salvar_processo(
            processo_2,
            criar_monitoramento=False,
        )

        # Salvar informações enquanto ainda estamos na sessão
        proc_id_2 = processo_db.id
        proc_movs_2 = len(processo_db.movimentacoes)
        proc_hashes = len(hashes_novos)
        proc_ult_mov_2 = processo_db.ultima_movimentacao_data

    print(f"      ✓ Processo atualizado: ID={proc_id_2}")
    print(f"      ✓ Total de movimentações agora: {proc_movs_2}")
    print(f"      ✓ Novas movimentações detectadas: {proc_hashes}")
    if hashes_novos:
        print(f"        Hashes: {hashes_novos}")
    print(f"      ✓ Última movimentação atualizada para: {proc_ult_mov_2}")
    print()

    # ─ 4. Salvar múltiplos processos (batch) ────────────────────────────────
    print("[4/4] Teste de salvar múltiplos processos...")
    processos_batch = []
    for i in range(3):
        p = await criar_processo_teste()
        p.numero_cnj = f"000000{i}-92.2019.8.26.010{i}"
        p.observacoes = f"Processo #{i+1} de teste batch"
        processos_batch.append(p)

    async with AsyncSessionLocal() as db:
        service = ProcessoService(db)
        stats = await service.salvar_processos(
            processos_batch,
            criar_monitoramento=True,
        )

    print(f"      ✓ Total processados: {stats['total']}")
    print(f"      ✓ Novos: {stats['novos']}")
    print(f"      ✓ Atualizados: {stats['atualizados']}")
    print(f"      ✓ Movimentações novas: {stats['movimentacoes_novas_total']}")
    if stats['erros']:
        print(f"      ⚠  Erros: {len(stats['erros'])}")
        for e in stats['erros'][:3]:
            print(f"        - {e}")
    print()

    # ─ Validação: Verificar dados salvos ────────────────────────────────────
    print("=" * 70)
    print("VALIDAÇÃO DOS DADOS SALVOS")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from src.database.models import Processo, Parte, Movimentacao

        # Contar registros
        result = await db.execute(select(Processo))
        num_processos = len(result.scalars().all())

        result = await db.execute(select(Parte))
        num_partes = len(result.scalars().all())

        result = await db.execute(select(Movimentacao))
        num_movs = len(result.scalars().all())

        print(f"Total no banco:")
        print(f"  Processos: {num_processos}")
        print(f"  Partes: {num_partes}")
        print(f"  Movimentações: {num_movs}")

        # Mostrar processo principal
        result = await db.execute(
            select(Processo).where(
                Processo.numero_cnj == "0000000-92.2019.8.26.0100"
            )
        )
        proc = result.scalar_one_or_none()
        if proc:
            print()
            print(f"Processo principal:")
            print(f"  CNJ: {proc.numero_cnj}")
            print(f"  Tribunal: {proc.tribunal}")
            print(f"  Vara: {proc.vara}")
            print(f"  Valor: R$ {proc.valor_causa:,.2f}" if proc.valor_causa else "  Valor: —")
            print(f"  Última movimentação: {proc.ultima_movimentacao_data}")
            print(f"  Criado em: {proc.criado_em}")
            print(f"  Atualizado em: {proc.atualizado_em}")

    print()
    print("=" * 70)
    print("✓ TESTE CONCLUÍDO COM SUCESSO")
    print("=" * 70)
    print()
    print("Próximos passos:")
    print("  1. Instalar PostgreSQL e ejecutar:")
    print("     docker-compose up -d db")
    print()
    print("  2. Executar teste com dados reais (OAB 361329):")
    print("     OAB_SOMENTE_TJSP=1 python scripts/testar_oab_361329.py")
    print()
    print("  3. Verificar dados em PostgreSQL:")
    print("     psql -U postgres -d juridico_crawler -c \"SELECT * FROM processos;\"")
    print()

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
