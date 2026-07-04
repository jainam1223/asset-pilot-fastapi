from fastapi import APIRouter

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.dashboard import router as dashboard_router
from app.api.v1.routers.dropdowns import router as dropdowns_router
from app.api.v1.routers.extensions import router as extensions_router
from app.api.v1.routers.handovers import router as handovers_router
from app.api.v1.routers.items import router as items_router
from app.api.v1.routers.requests import router as requests_router
from app.api.v1.routers.shipping import router as shipping_router
from app.api.v1.routers.support import router as support_router
from app.api.v1.routers.users import router as users_router

api_v1_router = APIRouter()
api_v1_router.include_router(auth_router)
api_v1_router.include_router(dashboard_router)
api_v1_router.include_router(dropdowns_router)
api_v1_router.include_router(extensions_router)
api_v1_router.include_router(handovers_router)
api_v1_router.include_router(items_router)
api_v1_router.include_router(requests_router)
api_v1_router.include_router(shipping_router)
api_v1_router.include_router(support_router)
api_v1_router.include_router(users_router)
