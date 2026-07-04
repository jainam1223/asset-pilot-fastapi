"""Trivial vertical-slice route proving API -> Service -> Repository ->
Redis wiring, returned via the standard response envelope. Not a real
domain feature.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.v1.dependencies import PingServiceDep
from app.schemas.ping import PingResponseSchema
from app.utils.response import success_response

router = APIRouter(prefix="/ping", tags=["ping"])


@router.get("")
async def ping(ping_service: PingServiceDep) -> JSONResponse:
    result = await ping_service.ping()
    schema = PingResponseSchema(message=result.message, count=result.count)
    return success_response(data=schema.model_dump(), message="pong")
