import pytest
from fastapi.testclient import TestClient

from api.app import app

# 2026-11-12 사용자가 정한 입력 정책 (AGENTS.md 계약에 아직 반영되지 않음):
# - 무한대·NaN 은 숫자가 아니다 → 422
# - 따옴표 친 숫자("2")와 true/false 는 숫자가 아니다 → 422
# - distance_km 는 20km 이하만 받는다. 20km 초과 → 422 (20km 는 허용: 10 + 3*20 = 70분)
# - 계약에 없는 필드가 섞이면 → 422


@pytest.fixture
def client() -> TestClient:
    """서버 오류(500)를 예외 대신 응답으로 받아 상태 코드를 비교할 수 있는 TestClient."""
    return TestClient(app, raise_server_exceptions=False)


def post_raw(client: TestClient, body: str):
    """JSON 표준 밖의 리터럴(NaN, Infinity)을 그대로 실어 /eta 에 보낸다."""
    return client.post(
        "/eta", content=body, headers={"content-type": "application/json"}
    )


@pytest.mark.parametrize(
    "body",
    [
        '{"distance_km": NaN, "pending_orders": 1}',
        '{"distance_km": Infinity, "pending_orders": 1}',
        '{"distance_km": -Infinity, "pending_orders": 1}',
        '{"distance_km": 1e309, "pending_orders": 1}',
        '{"distance_km": "inf", "pending_orders": 1}',
        '{"distance_km": 1, "pending_orders": NaN}',
        '{"distance_km": 1, "pending_orders": Infinity}',
    ],
    ids=[
        "distance-nan",
        "distance-infinity",
        "distance-negative-infinity",
        "distance-overflow-literal",
        "distance-inf-string",
        "orders-nan",
        "orders-infinity",
    ],
)
def test_eta_non_finite_returns_422(client: TestClient, body: str) -> None:
    """무한대와 NaN 은 숫자로 보지 않고 422 로 거부한다."""
    assert post_raw(client, body).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": "2", "pending_orders": 1},
        {"distance_km": " 2 ", "pending_orders": 1},
        {"distance_km": 1, "pending_orders": "3"},
        {"distance_km": True, "pending_orders": 1},
        {"distance_km": 1, "pending_orders": True},
        {"distance_km": 1, "pending_orders": False},
    ],
    ids=[
        "distance-quoted",
        "distance-quoted-spaces",
        "orders-quoted",
        "distance-true",
        "orders-true",
        "orders-false",
    ],
)
def test_eta_quoted_number_or_bool_returns_422(
    client: TestClient, payload: dict
) -> None:
    """따옴표 친 숫자와 true/false 는 숫자가 아니므로 422 로 거부한다."""
    assert client.post("/eta", json=payload).status_code == 422


def test_eta_distance_at_20km_is_allowed(client: TestClient) -> None:
    """거리 상한인 20km 는 받아들이고 규칙대로 70분(10 + 3*20)을 돌려준다."""
    res = client.post("/eta", json={"distance_km": 20, "pending_orders": 0})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(70.0)


@pytest.mark.parametrize(
    "distance_km",
    [20.001, 21, 1000, 1e308],
    ids=["just-over", "21km", "1000km", "float-max-range"],
)
def test_eta_distance_over_20km_returns_422(
    client: TestClient, distance_km: float
) -> None:
    """20km 를 넘는 거리는 422 로 거부한다."""
    res = client.post("/eta", json={"distance_km": distance_km, "pending_orders": 0})
    assert res.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": 1, "pending_orders": 1, "tip": 1000},
        {"distance_km": 1, "pending_orders": 1, "Distance_KM": 5},
    ],
    ids=["extra-field", "case-variant-field"],
)
def test_eta_unknown_field_returns_422(client: TestClient, payload: dict) -> None:
    """계약에 없는 필드가 섞인 요청은 422 로 거부한다."""
    assert client.post("/eta", json=payload).status_code == 422
