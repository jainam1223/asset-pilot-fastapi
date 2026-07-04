"""Pydantic-level business rules for the inventory schemas — pure schema
validation, no DB/HTTP involved.
"""

import uuid

import pytest
from pydantic import ValidationError

from app.models.enums import DeviceStatus, OwnerType
from app.schemas.item import ChangeItemStatusRequest, CreateItemRequest, UpdateItemRequest

pytestmark = pytest.mark.unit


def test_create_item_requires_client_name_when_owner_type_is_client() -> None:
    with pytest.raises(ValidationError):
        CreateItemRequest(
            name="Laptop",
            serial_no="SN-1",
            category_id=uuid.uuid4(),
            owner_type=OwnerType.CLIENT,
        )


def test_create_item_allows_missing_client_name_for_company_owner() -> None:
    request = CreateItemRequest(
        name="Laptop", serial_no="SN-1", category_id=uuid.uuid4(), owner_type=OwnerType.COMPANY
    )
    assert request.client_name is None


def test_update_item_rejects_explicit_null_name() -> None:
    with pytest.raises(ValidationError):
        UpdateItemRequest(name=None)


def test_update_item_rejects_explicit_null_category_id() -> None:
    with pytest.raises(ValidationError):
        UpdateItemRequest(category_id=None)


def test_update_item_allows_omitted_fields() -> None:
    request = UpdateItemRequest()
    assert request.model_dump(exclude_unset=True) == {}


def test_update_item_allows_explicit_null_client_name() -> None:
    request = UpdateItemRequest(client_name=None)
    assert "client_name" in request.model_fields_set


def test_change_status_rejects_lifecycle_managed_statuses() -> None:
    with pytest.raises(ValidationError):
        ChangeItemStatusRequest(status=DeviceStatus.ASSIGNED)


def test_change_status_allows_lost() -> None:
    request = ChangeItemStatusRequest(status=DeviceStatus.LOST)
    assert request.status == DeviceStatus.LOST
