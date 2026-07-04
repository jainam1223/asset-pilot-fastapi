from fastapi import APIRouter

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.ping import router as ping_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(ping_router)
