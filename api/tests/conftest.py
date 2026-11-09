import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


@pytest.fixture()
def client_factory():
    """Create a test client with custom settings, e.g. client_factory(api_key="secret")."""

    def make(**settings) -> TestClient:
        app.dependency_overrides[get_settings] = lambda: Settings(**settings)
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()


@pytest.fixture()
def client(client_factory):
    return client_factory()
