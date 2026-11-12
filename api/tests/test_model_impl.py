import importlib
import sys
import types
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

import api.app

# 계약: 응답의 model 은 "<구현체 이름>" 이다. 구현체는 MODEL_IMPL 환경변수로 고른다.
# 실제 구현체는 rule 하나뿐이라, 테스트 안에서만 쓰는 가짜 구현체 "fake" 를 끼워 넣는다.
FAKE_MINUTES = 42.0


@pytest.fixture
def fake_impl_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """MODEL_IMPL=fake 로 앱을 다시 불러온 TestClient. 끝나면 rule 로 되돌린다."""
    fake = types.ModuleType("api.predictors.fake")
    fake.estimate_delivery_minutes = lambda distance_km, pending_orders: FAKE_MINUTES
    monkeypatch.setitem(sys.modules, "api.predictors.fake", fake)
    monkeypatch.setenv("MODEL_IMPL", "fake")
    app_module = importlib.reload(api.app)
    try:
        yield TestClient(app_module.app)
    finally:
        monkeypatch.undo()
        importlib.reload(api.app)


def test_health_reports_selected_impl(fake_impl_client: TestClient) -> None:
    """/health 는 MODEL_IMPL 로 고른 구현체 이름을 알려 준다."""
    res = fake_impl_client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model": "fake"}


def test_eta_uses_selected_impl(fake_impl_client: TestClient) -> None:
    """/eta 는 MODEL_IMPL 로 고른 구현체로 계산하고 그 이름을 model 에 담는다."""
    res = fake_impl_client.post("/eta", json={"distance_km": 2, "pending_orders": 3})
    assert res.status_code == 200
    assert res.json() == {"minutes": FAKE_MINUTES, "model": "fake"}


def test_default_impl_restored_after_switch(client: TestClient) -> None:
    """구현체를 바꾼 테스트가 끝나면 기본 구현체 rule 로 돌아와 있다."""
    assert client.get("/health").json()["model"] == "rule"
