"""Pydantic-level business rules for the assignment schemas — pure schema
validation, no DB/HTTP involved.

Covers the naive/aware datetime normalization added after a mixed
naive+aware `assigned_from`/`assigned_to` payload crashed the
`>=` comparison in `_from_before_to` with a 500 instead of a 422.
"""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas.assignment import AssignRequestRequest, BookingRangeRequest, DirectAssignRequest

pytestmark = pytest.mark.unit


def test_assign_request_accepts_mixed_naive_and_aware_datetimes() -> None:
    request = AssignRequestRequest(
        item_id=uuid.uuid4(),
        assigned_from="2026-07-05T10:00:00",
        assigned_to="2026-07-06T10:00:00Z",
    )
    assert request.assigned_from.tzinfo is not None
    assert request.assigned_to.tzinfo is not None
    assert request.assigned_from < request.assigned_to


def test_assign_request_naive_datetime_is_treated_as_utc() -> None:
    request = AssignRequestRequest(
        item_id=uuid.uuid4(),
        assigned_from="2026-07-05T10:00:00",
        assigned_to="2026-07-06T10:00:00",
    )
    assert request.assigned_from == datetime(2026, 7, 5, 10, 0, 0, tzinfo=UTC)
    assert request.assigned_to == datetime(2026, 7, 6, 10, 0, 0, tzinfo=UTC)


def test_assign_request_rejects_equal_mixed_tz_datetimes_without_crashing() -> None:
    with pytest.raises(ValidationError, match="assigned_from must be before assigned_to"):
        AssignRequestRequest(
            item_id=uuid.uuid4(),
            assigned_from="2026-07-05T10:00:00",
            assigned_to="2026-07-05T10:00:00Z",
        )


def test_assign_request_rejects_from_after_to() -> None:
    with pytest.raises(ValidationError, match="assigned_from must be before assigned_to"):
        AssignRequestRequest(
            item_id=uuid.uuid4(),
            assigned_from="2026-07-06T10:00:00Z",
            assigned_to="2026-07-05T10:00:00",
        )


def test_booking_range_accepts_mixed_naive_and_aware_datetimes() -> None:
    request = BookingRangeRequest(
        assigned_from="2026-07-05T10:00:00",
        assigned_to="2026-07-06T10:00:00Z",
    )
    assert request.assigned_from < request.assigned_to


def test_booking_range_rejects_equal_mixed_tz_datetimes_without_crashing() -> None:
    with pytest.raises(ValidationError, match="assigned_from must be before assigned_to"):
        BookingRangeRequest(
            assigned_from="2026-07-05T10:00:00",
            assigned_to="2026-07-05T10:00:00Z",
        )


def test_direct_assign_accepts_mixed_naive_and_aware_datetimes() -> None:
    request = DirectAssignRequest(
        employee_id=uuid.uuid4(),
        assigned_from="2026-07-05T10:00:00",
        assigned_to="2026-07-06T10:00:00Z",
    )
    assert request.assigned_from < request.assigned_to


def test_direct_assign_rejects_equal_mixed_tz_datetimes_without_crashing() -> None:
    with pytest.raises(ValidationError, match="assigned_from must be before assigned_to"):
        DirectAssignRequest(
            employee_id=uuid.uuid4(),
            assigned_from="2026-07-05T10:00:00",
            assigned_to="2026-07-05T10:00:00Z",
        )
