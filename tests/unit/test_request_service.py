"""`RequestService` logic exercised against in-memory fake repositories (no
DB, no HTTP) — mirrors `tests/unit/test_user_service.py`'s pattern. Only
the guard logic that lives in the service (reject/cancel/escalate status
checks + manager_id default) is covered here; listing/sorting/filtering
live in `RequestRepository` and are covered by the integration tests.
"""

import itertools
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictException, NotFoundException
from app.models.enums import MgrApprovalStatus, RejectedByEnum, RequestPriority, RequestStatus
from app.models.request import Request
from app.models.user import User
from app.repositories.request_repository import RequestDetailRow, RequestListRow, RequestRepository
from app.repositories.user_repository import UserRepository
from app.services.request_service import RequestService
from app.utils.pagination import Page, PaginationParams

pytestmark = pytest.mark.unit

_ts_counter = itertools.count(1)


def _next_ts() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=next(_ts_counter))


def _make_request(*, status: RequestStatus = RequestStatus.PENDING_IT_APPROVAL, **kwargs: object) -> Request:
    return Request(
        id=kwargs.get("id", uuid.uuid4()),
        requester_id=kwargs.get("requester_id", uuid.uuid4()),
        category_id=kwargs.get("category_id", uuid.uuid4()),
        requested_from=_next_ts(),
        requested_to=_next_ts(),
        status=status,
        priority=kwargs.get("priority", RequestPriority.MEDIUM),
        requires_mgr_approval=kwargs.get("requires_mgr_approval", False),
        manager_id=kwargs.get("manager_id"),
        created_at=_next_ts(),
        updated_at=_next_ts(),
    )


def _make_user(*, manager_id: uuid.UUID | None = None) -> User:
    return User(
        id=uuid.uuid4(),
        name="Requester",
        email=f"{uuid.uuid4().hex}@techcorp.internal",
        password_hash="hash",
        manager_id=manager_id,
        is_active=True,
    )


class FakeRequestRepository(RequestRepository):
    def __init__(
        self, requests: Iterable[Request] = (), *, detail_row: RequestDetailRow | None = None
    ) -> None:
        self._requests: dict[uuid.UUID, Request] = {r.id: r for r in requests}
        self._detail_row = detail_row

    async def get_by_id(self, id_: uuid.UUID) -> Request | None:
        return self._requests.get(id_)

    async def update(self, entity: Request) -> Request:
        entity.updated_at = _next_ts()
        self._requests[entity.id] = entity
        return entity

    async def get_detail(self, request_id: uuid.UUID) -> RequestDetailRow | None:
        return self._detail_row

    async def list_requests(
        self,
        *,
        status: RequestStatus | None,
        category_id: uuid.UUID | None,
        priority: RequestPriority | None,
        requested_from: datetime | None,
        requested_to: datetime | None,
        search: str | None,
        pagination: PaginationParams,
    ) -> Page[RequestListRow]:
        return Page(items=[], total_items=0, page=pagination.page, page_size=pagination.page_size)

    async def list_it_approvals(self, *, pagination: PaginationParams) -> Page[RequestListRow]:
        return Page(items=[], total_items=0, page=pagination.page, page_size=pagination.page_size)


class FakeUserRepository(UserRepository):
    def __init__(self, users: Iterable[User] = ()) -> None:
        self._users: dict[uuid.UUID, User] = {u.id: u for u in users}

    async def get_by_id(self, id_: uuid.UUID) -> User | None:
        return self._users.get(id_)


async def test_reject_on_non_pending_it_approval_status_raises_conflict() -> None:
    request = _make_request(status=RequestStatus.ASSIGNED)
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository())

    with pytest.raises(ConflictException):
        await service.reject(
            request.id, rejected_reason="not needed", it_decision_note=None, actor_id=uuid.uuid4()
        )


async def test_reject_pending_it_approval_sets_rejected_by_it_admin() -> None:
    request = _make_request(status=RequestStatus.PENDING_IT_APPROVAL)
    actor_id = uuid.uuid4()
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository())

    result = await service.reject(
        request.id, rejected_reason="out of budget", it_decision_note="see policy", actor_id=actor_id
    )

    assert result.status == RequestStatus.REJECTED
    assert result.rejected_by == RejectedByEnum.IT_ADMIN
    assert result.rejected_reason == "out of budget"
    assert result.it_decision_note == "see policy"
    assert result.it_decided_by == actor_id
    assert result.it_decided_at is not None


async def test_reject_missing_request_raises_not_found() -> None:
    service = RequestService(FakeRequestRepository(), FakeUserRepository())

    with pytest.raises(NotFoundException):
        await service.reject(uuid.uuid4(), rejected_reason="x", it_decision_note=None, actor_id=uuid.uuid4())


@pytest.mark.parametrize("status", [RequestStatus.COMPLETED, RequestStatus.REJECTED, RequestStatus.CANCELLED])
async def test_cancel_terminal_request_raises_conflict(status: RequestStatus) -> None:
    request = _make_request(status=status)
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository())

    with pytest.raises(ConflictException):
        await service.cancel(request.id, rejected_reason="no longer needed", actor_id=uuid.uuid4())


async def test_cancel_non_terminal_request_sets_rejected_by_it_admin_cancel() -> None:
    request = _make_request(status=RequestStatus.REQUESTED)
    actor_id = uuid.uuid4()
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository())

    result = await service.cancel(request.id, rejected_reason="duplicate request", actor_id=actor_id)

    assert result.status == RequestStatus.CANCELLED
    assert result.rejected_by == RejectedByEnum.IT_ADMIN_CANCEL
    assert result.cancelled_by == actor_id
    assert result.cancelled_at is not None


async def test_escalate_defaults_manager_id_from_requester() -> None:
    manager_id = uuid.uuid4()
    requester = _make_user(manager_id=manager_id)
    request = _make_request(status=RequestStatus.PENDING_IT_APPROVAL, requester_id=requester.id)
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository([requester]))

    result = await service.escalate_to_manager(request.id, manager_id=None)

    assert result.manager_id == manager_id
    assert result.status == RequestStatus.PENDING_MGR_APPROVAL
    assert result.mgr_approval_status == MgrApprovalStatus.PENDING
    assert result.requires_mgr_approval is True


async def test_escalate_uses_explicit_manager_id_over_requester_default() -> None:
    requester = _make_user(manager_id=uuid.uuid4())
    explicit_manager_id = uuid.uuid4()
    request = _make_request(status=RequestStatus.PENDING_IT_APPROVAL, requester_id=requester.id)
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository([requester]))

    result = await service.escalate_to_manager(request.id, manager_id=explicit_manager_id)

    assert result.manager_id == explicit_manager_id


async def test_escalate_already_requiring_mgr_approval_raises_conflict() -> None:
    request = _make_request(status=RequestStatus.PENDING_IT_APPROVAL, requires_mgr_approval=True)
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository())

    with pytest.raises(ConflictException):
        await service.escalate_to_manager(request.id, manager_id=None)


async def test_escalate_wrong_status_raises_conflict() -> None:
    request = _make_request(status=RequestStatus.REQUESTED)
    service = RequestService(FakeRequestRepository([request]), FakeUserRepository())

    with pytest.raises(ConflictException):
        await service.escalate_to_manager(request.id, manager_id=uuid.uuid4())


async def test_get_detail_missing_request_raises_not_found() -> None:
    service = RequestService(FakeRequestRepository(detail_row=None), FakeUserRepository())

    with pytest.raises(NotFoundException):
        await service.get_detail(uuid.uuid4())


async def test_list_requests_delegates_to_repository_with_filters() -> None:
    service = RequestService(FakeRequestRepository(), FakeUserRepository())

    page = await service.list_requests(
        status=RequestStatus.REQUESTED,
        category_id=None,
        priority=None,
        requested_from=None,
        requested_to=None,
        search=None,
        pagination=PaginationParams(),
    )

    assert page.items == []
    assert page.total_items == 0
