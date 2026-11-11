import pytest
from fastapi.testclient import TestClient

# 기본 구현체(rule)의 계약: 기본 10분 + 1km당 3분 + 대기 주문 1건당 2분


def test_health_returns_ok_and_model_name(client: TestClient) -> None:
    """/health 는 200 과 status=ok, 구현체 이름을 돌려준다."""
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "model": "rule"}


def test_eta_response_shape(client: TestClient) -> None:
    """/eta 응답은 minutes(숫자)와 model(문자열) 두 필드만 가진다."""
    res = client.post("/eta", json={"distance_km": 2, "pending_orders": 3})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"minutes", "model"}
    assert isinstance(body["minutes"], (int, float))
    assert body["model"] == "rule"


@pytest.mark.parametrize(
    ("distance_km", "pending_orders", "expected"),
    [
        (2, 3, 22.0),
        (1.5, 0, 14.5),
        (0, 4, 18.0),
    ],
)
def test_eta_known_inputs(
    client: TestClient, distance_km: float, pending_orders: int, expected: float
) -> None:
    """알려진 정상 입력에 대해 예상 시간이 계약대로 계산된다."""
    res = client.post(
        "/eta", json={"distance_km": distance_km, "pending_orders": pending_orders}
    )
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(expected)


def test_eta_zero_inputs(client: TestClient) -> None:
    """거리 0, 대기 주문 0 이면 기본 시간 10분을 돌려준다."""
    res = client.post("/eta", json={"distance_km": 0, "pending_orders": 0})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(10.0)


def test_eta_large_inputs(client: TestClient) -> None:
    """큰 입력값도 거부하지 않고 계약대로 계산한다."""
    res = client.post("/eta", json={"distance_km": 1000, "pending_orders": 10000})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(10 + 3 * 1000 + 2 * 10000)


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": "far", "pending_orders": 1},
        {"distance_km": 1, "pending_orders": "many"},
        {"distance_km": -0.1, "pending_orders": 1},
        {"distance_km": 1, "pending_orders": -1},
        {"distance_km": 1},
        {"pending_orders": 1},
        {},
    ],
    ids=[
        "distance-not-number",
        "orders-not-number",
        "distance-negative",
        "orders-negative",
        "missing-orders",
        "missing-distance",
        "empty-body",
    ],
)
def test_eta_invalid_input_returns_422(client: TestClient, payload: dict) -> None:
    """숫자가 아니거나 음수이거나 빠진 필드는 422 로 거부된다."""
    res = client.post("/eta", json=payload)
    assert res.status_code == 422
