"""Enveloppe de pagination générique (app.schemas.pagination)."""

from app.schemas.pagination import Page


def test_page_of_computes_total_pages_rounded_up() -> None:
    page = Page[int].of([1, 2, 3], page=1, page_size=20, total=45)

    assert page.items == [1, 2, 3]
    assert page.pagination.page == 1
    assert page.pagination.page_size == 20
    assert page.pagination.total == 45
    assert page.pagination.total_pages == 3


def test_page_of_exact_multiple_does_not_add_an_extra_page() -> None:
    page = Page[int].of([], page=2, page_size=20, total=40)

    assert page.pagination.total_pages == 2


def test_page_of_empty_result_has_zero_total_pages() -> None:
    page = Page[str].of([], page=1, page_size=20, total=0)

    assert page.pagination.total_pages == 0


def test_page_serializes_to_the_expected_envelope_shape() -> None:
    page = Page[int].of([1], page=1, page_size=20, total=1)

    body = page.model_dump(mode="json")

    assert body == {
        "items": [1],
        "pagination": {"page": 1, "page_size": 20, "total": 1, "total_pages": 1},
    }
