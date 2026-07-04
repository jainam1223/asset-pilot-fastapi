from pydantic import BaseModel


class DependencyCheckSchema(BaseModel):
    status: str
    latency_ms: float | None
    error: str | None


class ReadinessSchema(BaseModel):
    status: str
    timestamp: str
    checks: dict[str, DependencyCheckSchema]


class LivenessSchema(BaseModel):
    status: str
