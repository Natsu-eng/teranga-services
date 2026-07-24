from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class Trade(UUIDPrimaryKeyMixin, Base):
    """Métier exercé par un artisan (ou demandé par un client).

    Table de référence, pas un enum : les métiers s'ajoutent en continu, sans
    migration de schéma, et leur libellé est prévu pour l'i18n Wolof
    (BUILD_PLAN.md §2.2).
    """

    __tablename__ = "trade"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    label_fr: Mapped[str] = mapped_column(String(100), nullable=False)
    label_wo: Mapped[str | None] = mapped_column(String(100))
    icon: Mapped[str | None] = mapped_column(String(100))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
