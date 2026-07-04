import pytest

from app.utils.pagination import Page, PaginationParams

pytestmark = pytest.mark.unit


def test_pagination_params_offset_and_limit() -> None:
    params = PaginationParams(page=3, page_size=10)
    assert params.offset == 20
    assert params.limit == 10


def test_pagination_params_rejects_invalid_page() -> None:
    with pytest.raises(ValueError):
        PaginationParams(page=0)


@pytest.mark.parametrize(
    ("total_items", "page_size", "expected_pages"),
    [(0, 20, 0), (1, 20, 1), (20, 20, 1), (21, 20, 2), (134, 20, 7)],
)
def test_page_total_pages(total_items: int, page_size: int, expected_pages: int) -> None:
    page: Page[object] = Page(items=[], total_items=total_items, page=1, page_size=page_size)
    assert page.total_pages == expected_pages


def test_page_to_meta() -> None:
    page = Page(items=["a", "b"], total_items=134, page=1, page_size=20)
    meta = page.to_meta()
    assert meta.page == 1
    assert meta.page_size == 20
    assert meta.total_items == 134
    assert meta.total_pages == 7
