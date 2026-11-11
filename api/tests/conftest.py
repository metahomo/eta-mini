import pytest
from fastapi.testclient import TestClient

from api.app import app


@pytest.fixture
def client() -> TestClient:
    """실제 서버 없이 앱에 요청을 보내는 TestClient."""
    return TestClient(app)
