"""
Testes de integração para os endpoints da API REST.
Usa banco SQLite em memória para isolamento.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base
from src.main import app
from src.database.connection import get_db

# Engine SQLite em memória para testes
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(autouse=True)
async def setup_banco():
    """Cria as tabelas antes de cada teste e limpa depois."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Cliente HTTP assíncrono para a API."""
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as c:
        yield c
    app.dependency_overrides.clear()


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestTribunais:
    @pytest.mark.asyncio
    async def test_lista_tribunais(self, client: AsyncClient):
        resp = await client.get("/tribunais")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 80
        assert "tjsp" in data["tribunais"]
        assert "stj" in data["tribunais"]


class TestProcessosEndpoints:
    @pytest.mark.asyncio
    async def test_listar_processos_vazio(self, client: AsyncClient):
        resp = await client.get("/processos/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["processos"] == []

    @pytest.mark.asyncio
    async def test_buscar_numero_cnj_invalido(self, client: AsyncClient):
        resp = await client.post("/processos/buscar", json={
            "numero_cnj": "numero-invalido",
            "tribunal": "tjsp",
        })
        assert resp.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_obter_processo_inexistente(self, client: AsyncClient):
        resp = await client.get("/processos/0001234-56.2024.8.26.0001")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_deletar_processo_inexistente(self, client: AsyncClient):
        resp = await client.delete("/processos/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_listar_com_filtro_tribunal(self, client: AsyncClient):
        resp = await client.get("/processos/?tribunal=tjsp&limite=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "processos" in data


class TestPartesEndpoints:
    @pytest.mark.asyncio
    async def test_listar_partes_processo_inexistente(self, client: AsyncClient):
        resp = await client.get("/partes/processo/9999")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_buscar_sem_parametros(self, client: AsyncClient):
        resp = await client.get("/partes/buscar")
        assert resp.status_code == 400
        assert "parâmetro" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_buscar_por_nome(self, client: AsyncClient):
        resp = await client.get("/partes/buscar?nome=silva")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_buscar_por_oab(self, client: AsyncClient):
        resp = await client.get("/partes/buscar?oab=123456SP")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


class TestMonitoramentoEndpoints:
    @pytest.mark.asyncio
    async def test_listar_monitoramentos_vazio(self, client: AsyncClient):
        resp = await client.get("/monitoramento/")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_criar_monitoramento_processo_inexistente(self, client: AsyncClient):
        resp = await client.post("/monitoramento/", json={"processo_id": 9999})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_obter_monitoramento_inexistente(self, client: AsyncClient):
        resp = await client.get("/monitoramento/9999")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_desativar_monitoramento_inexistente(self, client: AsyncClient):
        resp = await client.delete("/monitoramento/9999")
        assert resp.status_code == 404
