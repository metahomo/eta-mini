import importlib
import math
import os
from typing import Any
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
MODEL_IMPL = os.getenv("MODEL_IMPL", "rule")
estimate_delivery_minutes = importlib.import_module(f"api.predictors.{MODEL_IMPL}").estimate_delivery_minutes
MAX_DISTANCE_KM = 20 # 사장님 결정: 20km 초과 배달은 받지 않는다
class EtaRequest(BaseModel):
 """배달 예상 시간 요청"""
 # strict: "2" 같은 문자열과 true/false 를 숫자로 바꾸지 않는다
 # extra=forbid: 계약에 없는 필드가 섞이면 거부한다
 # allow_inf_nan=False: 무한대·NaN 은 숫자로 보지 않는다
 model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
 # 모델이 더 많은 정보를 원하면 여기에 필드를 추가
 distance_km: float = Field(ge=0, le=MAX_DISTANCE_KM, description="가게에서 배달지까지 거리(km)")
 pending_orders: int = Field(ge=0, description="지금 밀려 있는 주문 수")
class EtaResponse(BaseModel):
 """배달 예상 시간 응답"""
 minutes: float
 model: str # 어떤 구현체가 낸 예측인지 (장애 추적용)

app = FastAPI(title="delivery-eta")
def _json_safe(value: Any) -> Any:
 """JSON 으로 쓸 수 없는 무한대·NaN 을 문자열로 바꾼다."""
 if isinstance(value, float) and not math.isfinite(value):
  return str(value)
 if isinstance(value, dict):
  return {k: _json_safe(v) for k, v in value.items()}
 if isinstance(value, list):
  return [_json_safe(v) for v in value]
 return value
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
 """422 응답에 되돌려 주는 입력값이 NaN·무한대여도 500 이 나지 않게 한다."""
 return JSONResponse(status_code=422, content={"detail": _json_safe(jsonable_encoder(exc.errors()))})
@app.get("/health")
def health() -> dict[str, str]:
 """서비스 상태와 현재 구현체 이름을 돌려준다."""
 return {"status": "ok", "model": MODEL_IMPL}
@app.post("/eta", response_model=EtaResponse)
def eta(req: EtaRequest) -> EtaResponse:
 """배달 예상 시간을 계산"""
 minutes = estimate_delivery_minutes(req.distance_km, req.pending_orders)
 return EtaResponse(minutes=minutes, model=MODEL_IMPL)
