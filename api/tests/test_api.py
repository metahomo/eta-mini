import pytest
from fastapi.testclient import TestClient

# 기대값은 AGENTS.md "API 계약"의 사장님 규칙 표에서 손으로 계산한 값이다.
# 규칙: 기본 10분 + 1km당 3분 + 대기 주문 1건당 2분 (기본 구현체 rule 기준)


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
    """거리 상한(20km)과 아주 많은 대기 주문도 계약대로 계산한다."""
    # 원래 계약 표의 1000km 행은 2026-11-12 결정한 20km 상한으로 대체됐다: 10 + 60 + 20000
    res = client.post("/eta", json={"distance_km": 20, "pending_orders": 10000})
    assert res.status_code == 200
    assert res.json()["minutes"] == pytest.approx(20070.0)


@pytest.mark.parametrize(
    "payload",
    [
        {"distance_km": "far", "pending_orders": 1},
        {"distance_km": 1, "pending_orders": "many"},
        {"distance_km": -0.1, "pending_orders": 1},
        {"distance_km": 1, "pending_orders": -1},
        {"distance_km": None, "pending_orders": 1},
        {"distance_km": 1, "pending_orders": None},
        {"distance_km": 1, "pending_orders": 1.5},
        {"distance_km": -0.01, "pending_orders": 1},
        {"distance_km": "", "pending_orders": 1},
        {"distance_km": [1], "pending_orders": 1},
        {"distance_km": {"km": 1}, "pending_orders": 1},
        {"distance_km": 1, "pending_orders": ""},
        {"distance_km": 1, "pending_orders": [1]},
        {"distance_km": 1, "pending_orders": {"n": 1}},
        {"distance_km": "NaN", "pending_orders": 1},
        {"distance_km": 1, "pending_orders": "1e2"},
        {"distance_km": 1},
        {"pending_orders": 1},
        {},
    ],
    ids=[
        "distance-not-number",
        "orders-not-number",
        "distance-negative",
        "orders-negative",
        "distance-null",
        "orders-null",
        "orders-not-integer",
        "distance-small-negative",
        "distance-empty-string",
        "distance-array",
        "distance-object",
        "orders-empty-string",
        "orders-array",
        "orders-object",
        "distance-nan-string",
        "orders-exponent-string",
        "missing-orders",
        "missing-distance",
        "empty-body",
    ],
)
def test_eta_invalid_input_returns_422(client: TestClient, payload: dict) -> None:
    """숫자가 아니거나 음수이거나 정수가 아니거나 빠진 필드는 422 로 거부된다."""
    res = client.post("/eta", json=payload)
    assert res.status_code == 422


def test_eta_non_json_body_returns_422(client: TestClient) -> None:
    """JSON 이 아닌 본문은 422 로 거부된다."""
    res = client.post(
        "/eta", content="not json", headers={"content-type": "application/json"}
    )
    assert res.status_code == 422


@pytest.mark.parametrize(
    "body",
    ["[1, 2]", "null", ""],
    ids=["json-array", "json-null", "empty"],
)
def test_eta_body_not_object_returns_422(client: TestClient, body: str) -> None:
    """본문이 객체가 아니거나(배열, null) 비어 있으면 422 로 거부된다."""
    res = client.post(
        "/eta", content=body, headers={"content-type": "application/json"}
    )
    assert res.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/eta"), ("POST", "/health")],
    ids=["get-eta", "post-health"],
)
def test_wrong_method_returns_405(client: TestClient, method: str, path: str) -> None:
    """계약에 없는 메서드로 부르면 405 를 돌려준다."""
    res = client.request(method, path)
    assert res.status_code == 405


def test_eta_each_pending_order_adds_two_minutes(client: TestClient) -> None:
    """같은 거리에서 대기 주문이 1건 늘면 예상 시간이 정확히 2분 늘어난다."""
    base = client.post("/eta", json={"distance_km": 2, "pending_orders": 3})
    more = client.post("/eta", json={"distance_km": 2, "pending_orders": 4})
    assert more.json()["minutes"] - base.json()["minutes"] == pytest.approx(2.0)


def test_eta_each_km_adds_three_minutes(client: TestClient) -> None:
    """같은 대기 주문 수에서 거리가 1km 늘면 예상 시간이 정확히 3분 늘어난다."""
    base = client.post("/eta", json={"distance_km": 2, "pending_orders": 3})
    more = client.post("/eta", json={"distance_km": 3, "pending_orders": 3})
    assert more.json()["minutes"] - base.json()["minutes"] == pytest.approx(3.0)


def test_eta_model_matches_health(client: TestClient) -> None:
    """/eta 의 model 은 /health 가 알려 주는 구현체 이름과 같다."""
    health_model = client.get("/health").json()["model"]
    res = client.post("/eta", json={"distance_km": 1, "pending_orders": 1})
    assert res.json()["model"] == health_model
