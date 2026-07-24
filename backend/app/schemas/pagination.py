"""Enveloppe de pagination générique, offset bornée (BUILD_PLAN.md §6, Lot 9).

Réutilisée par `GET /artisans` et `GET /artisans/{id}/reviews` -- une seule
définition de l'enveloppe `{ items, pagination }`, pas une par endpoint.
"""

from pydantic import BaseModel


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class Page[T](BaseModel):
    items: list[T]
    pagination: PaginationMeta

    @classmethod
    def of(cls, items: list[T], *, page: int, page_size: int, total: int) -> "Page[T]":
        total_pages = -(-total // page_size)  # division entière arrondie au-dessus
        return cls(
            items=items,
            pagination=PaginationMeta(
                page=page, page_size=page_size, total=total, total_pages=total_pages
            ),
        )
