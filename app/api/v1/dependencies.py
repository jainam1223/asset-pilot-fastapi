"""Single place where dependency injection is wired together.

Every provider a router needs — DB session, Redis client, repositories,
services — is resolved here and exposed as an `Annotated` alias. Routers
only ever import from this module (never construct a session/repository/
service themselves), so swapping an implementation is a one-file change.
"""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException
from app.core.security import TokenPayload, get_current_user
from app.db.redis import get_redis
from app.db.session import get_db_session
from app.models.enums import UserRole
from app.repositories.cache_repository import AbstractCacheRepository, RedisCacheRepository
from app.repositories.device_log_repository import DeviceLogRepository
from app.repositories.extension_request_repository import ExtensionRequestRepository
from app.repositories.handover_request_repository import HandoverRequestRepository
from app.repositories.health_repository import AbstractHealthRepository, HealthRepository
from app.repositories.item_category_repository import ItemCategoryRepository
from app.repositories.item_repository import ItemRepository
from app.repositories.request_repository import RequestRepository
from app.repositories.support_request_repository import SupportRequestRepository
from app.repositories.user_repository import UserRepository
from app.services.assignment_service import AssignmentService
from app.services.auth_service import AuthService
from app.services.dashboard_service import DashboardService
from app.services.device_log_service import DeviceLogService
from app.services.dropdown_service import DropdownService
from app.services.extension_service import ExtensionService
from app.services.handover_service import HandoverService
from app.services.health_service import HealthService
from app.services.inventory_service import InventoryService
from app.services.ping_service import PingService
from app.services.request_service import RequestService
from app.services.shipping_service import ShippingService
from app.services.support_service import SupportService
from app.services.user_service import UserService
from app.utils.pagination import PaginationParams

# --- Infra-level providers ---

DbSession = Annotated[AsyncSession, Depends(get_db_session)]
RedisClient = Annotated[Redis, Depends(get_redis)]
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


async def require_it_admin(current_user: CurrentUser) -> TokenPayload:
    """RBAC gate for every `/admin/*` router. Never trust a client-asserted
    role — this re-checks the `role` claim on the verified token itself.
    """
    if current_user.claims.get("role") != UserRole.IT_ADMIN.value:
        raise ForbiddenException(message="IT Admin role is required for this action.")
    return current_user


ITAdminUser = Annotated[TokenPayload, Depends(require_it_admin)]
PaginationDep = Annotated[PaginationParams, Depends()]


# --- Repository providers ---


def get_cache_repository(redis_client: RedisClient) -> AbstractCacheRepository:
    return RedisCacheRepository(redis_client)


CacheRepositoryDep = Annotated[AbstractCacheRepository, Depends(get_cache_repository)]


def get_health_repository(session: DbSession, cache: CacheRepositoryDep) -> AbstractHealthRepository:
    return HealthRepository(session, cache)


HealthRepositoryDep = Annotated[AbstractHealthRepository, Depends(get_health_repository)]


def get_user_repository(session: DbSession) -> UserRepository:
    return UserRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]


def get_device_log_repository(session: DbSession) -> DeviceLogRepository:
    return DeviceLogRepository(session)


DeviceLogRepositoryDep = Annotated[DeviceLogRepository, Depends(get_device_log_repository)]


def get_item_repository(session: DbSession) -> ItemRepository:
    return ItemRepository(session)


ItemRepositoryDep = Annotated[ItemRepository, Depends(get_item_repository)]


def get_item_category_repository(session: DbSession) -> ItemCategoryRepository:
    return ItemCategoryRepository(session)


ItemCategoryRepositoryDep = Annotated[ItemCategoryRepository, Depends(get_item_category_repository)]


def get_request_repository(session: DbSession) -> RequestRepository:
    return RequestRepository(session)


RequestRepositoryDep = Annotated[RequestRepository, Depends(get_request_repository)]


def get_support_request_repository(session: DbSession) -> SupportRequestRepository:
    return SupportRequestRepository(session)


SupportRequestRepositoryDep = Annotated[SupportRequestRepository, Depends(get_support_request_repository)]


def get_handover_request_repository(session: DbSession) -> HandoverRequestRepository:
    return HandoverRequestRepository(session)


HandoverRequestRepositoryDep = Annotated[HandoverRequestRepository, Depends(get_handover_request_repository)]


def get_extension_request_repository(session: DbSession) -> ExtensionRequestRepository:
    return ExtensionRequestRepository(session)


ExtensionRequestRepositoryDep = Annotated[
    ExtensionRequestRepository, Depends(get_extension_request_repository)
]


# --- Service providers ---


def get_health_service(health_repository: HealthRepositoryDep) -> HealthService:
    return HealthService(health_repository)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


def get_auth_service(user_repository: UserRepositoryDep) -> AuthService:
    return AuthService(user_repository)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_ping_service(cache_repository: CacheRepositoryDep) -> PingService:
    return PingService(cache_repository)


PingServiceDep = Annotated[PingService, Depends(get_ping_service)]


def get_device_log_service(device_log_repository: DeviceLogRepositoryDep) -> DeviceLogService:
    return DeviceLogService(device_log_repository)


DeviceLogServiceDep = Annotated[DeviceLogService, Depends(get_device_log_service)]


def get_inventory_service(
    item_repository: ItemRepositoryDep,
    item_category_repository: ItemCategoryRepositoryDep,
    user_repository: UserRepositoryDep,
    request_repository: RequestRepositoryDep,
    support_request_repository: SupportRequestRepositoryDep,
    handover_request_repository: HandoverRequestRepositoryDep,
    device_log_service: DeviceLogServiceDep,
) -> InventoryService:
    return InventoryService(
        item_repository,
        item_category_repository,
        user_repository,
        request_repository,
        support_request_repository,
        handover_request_repository,
        device_log_service,
    )


InventoryServiceDep = Annotated[InventoryService, Depends(get_inventory_service)]


def get_dropdown_service(
    item_category_repository: ItemCategoryRepositoryDep, user_repository: UserRepositoryDep
) -> DropdownService:
    return DropdownService(item_category_repository, user_repository)


DropdownServiceDep = Annotated[DropdownService, Depends(get_dropdown_service)]


def get_user_service(user_repository: UserRepositoryDep) -> UserService:
    return UserService(user_repository)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_request_service(
    request_repository: RequestRepositoryDep, user_repository: UserRepositoryDep
) -> RequestService:
    return RequestService(request_repository, user_repository)


RequestServiceDep = Annotated[RequestService, Depends(get_request_service)]


def get_assignment_service(
    item_repository: ItemRepositoryDep,
    request_repository: RequestRepositoryDep,
    user_repository: UserRepositoryDep,
    device_log_service: DeviceLogServiceDep,
) -> AssignmentService:
    return AssignmentService(item_repository, request_repository, user_repository, device_log_service)


AssignmentServiceDep = Annotated[AssignmentService, Depends(get_assignment_service)]


def get_shipping_service(
    request_repository: RequestRepositoryDep,
    item_repository: ItemRepositoryDep,
    support_request_repository: SupportRequestRepositoryDep,
    device_log_service: DeviceLogServiceDep,
) -> ShippingService:
    return ShippingService(
        request_repository, item_repository, support_request_repository, device_log_service
    )


ShippingServiceDep = Annotated[ShippingService, Depends(get_shipping_service)]


def get_support_service(
    support_request_repository: SupportRequestRepositoryDep,
    item_repository: ItemRepositoryDep,
    request_repository: RequestRepositoryDep,
    device_log_service: DeviceLogServiceDep,
) -> SupportService:
    return SupportService(support_request_repository, item_repository, request_repository, device_log_service)


SupportServiceDep = Annotated[SupportService, Depends(get_support_service)]


def get_extension_service(
    extension_request_repository: ExtensionRequestRepositoryDep,
    request_repository: RequestRepositoryDep,
    device_log_service: DeviceLogServiceDep,
) -> ExtensionService:
    return ExtensionService(extension_request_repository, request_repository, device_log_service)


ExtensionServiceDep = Annotated[ExtensionService, Depends(get_extension_service)]


def get_handover_service(handover_request_repository: HandoverRequestRepositoryDep) -> HandoverService:
    return HandoverService(handover_request_repository)


HandoverServiceDep = Annotated[HandoverService, Depends(get_handover_service)]


def get_dashboard_service(
    item_repository: ItemRepositoryDep,
    request_repository: RequestRepositoryDep,
    support_request_repository: SupportRequestRepositoryDep,
    handover_request_repository: HandoverRequestRepositoryDep,
    extension_request_repository: ExtensionRequestRepositoryDep,
) -> DashboardService:
    return DashboardService(
        item_repository,
        request_repository,
        support_request_repository,
        handover_request_repository,
        extension_request_repository,
    )


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
