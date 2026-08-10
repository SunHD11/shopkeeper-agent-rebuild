"""健康检查接口响应模型。"""

from typing import Literal

from pydantic import BaseModel, Field


class DependencyHealthSchema(BaseModel):
    """一个基础服务的可用状态和探测耗时。"""

    status: Literal["up", "down"]
    latency_ms: float = Field(ge=0)
    detail: str | None = None


class HealthSchema(BaseModel):
    """存活或就绪检查的统一响应。"""

    status: Literal["ok", "unavailable"]
    checks: dict[str, DependencyHealthSchema] = Field(default_factory=dict)
