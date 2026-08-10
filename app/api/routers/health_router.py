"""供容器、反向代理和运维系统调用的健康检查路由。"""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.dependencies import get_health_service
from app.api.schemas.health_schema import HealthSchema
from app.services.health_service import HealthService

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live", response_model=HealthSchema, summary="进程存活检查")
async def liveness_handler() -> HealthSchema:
    """只证明 FastAPI 事件循环能响应，不访问任何外部服务。"""

    return HealthSchema(status="ok")


@health_router.get(
    "/ready",
    response_model=HealthSchema,
    summary="在线问数依赖就绪检查",
    responses={503: {"model": HealthSchema}},
)
async def readiness_handler(
    health_service: Annotated[HealthService, Depends(get_health_service)],
) -> HealthSchema | JSONResponse:
    """全部基础服务可用时返回 200，任一不可用时返回 503。"""

    report = await health_service.check_readiness()
    response = HealthSchema.model_validate(asdict(report))
    if report.status == "unavailable":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(mode="json"),
        )
    return response
