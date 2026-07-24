"""Schémas Pydantic des contrats /api/v1/auth (BUILD_PLAN.md §3.2)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import Locale, Role


class RequestOtpIn(BaseModel):
    phone: str


class VerifyOtpIn(BaseModel):
    phone: str
    code: str


class RefreshIn(BaseModel):
    refresh: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    full_name: str
    role: Role
    locale: Locale
    phone_verified_at: datetime | None
    created_at: datetime


class TokenPairOut(BaseModel):
    access: str
    refresh: str


class AuthResponseOut(TokenPairOut):
    user: UserOut
