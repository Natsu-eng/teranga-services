from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class OtpCode(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """Code OTP pour la connexion par téléphone (BUILD_PLAN.md §4).

    Pas de FK vers `user` : un OTP peut être demandé pour un numéro qui n'a
    pas encore de compte (premier login = création de compte).
    """

    __tablename__ = "otp_code"

    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
