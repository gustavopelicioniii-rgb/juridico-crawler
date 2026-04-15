"""
Gerenciamento da conexão assíncrona com PostgreSQL via SQLAlchemy + asyncpg.
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings

# Configurações do Engine
engine_params = {
    "echo": settings.api_debug,
    "future": True,
}

# SQLite não suporta pool_size/max_overflow
if not settings.database_url.startswith("sqlite"):
    engine_params["pool_size"] = settings.database_pool_size
    engine_params["max_overflow"] = settings.database_max_overflow

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    **engine_params
)

# Factory de sessões assíncronas
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency injection para FastAPI."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Cria todas as tabelas (usado no startup). Inclui retentativas para aguardar o banco estar pronto."""
    from src.database.models import Base

    max_retries = 5
    for attempt in range(max_retries):
        try:
            print(f"Tentativa {attempt + 1}/{max_retries} de criar tabelas...")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            print("[OK] Todas as tabelas criadas com sucesso!")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  [AVISO] Erro: {e}")
                print(f"  Aguardando 2 segundos antes de tentar novamente...")
                await asyncio.sleep(2)
            else:
                print(f"\n[FALHA] Falha ao criar tabelas após {max_retries} tentativas!")
                raise
