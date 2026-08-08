"""Schémas Pydantic des contrats /api/v1/auth (BUILD_PLAN.md §3.2)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.enums import Locale, Role


class RequestOtpIn(BaseModel):
    phone: str


class VerifyOtpIn(BaseModel):
    phone: str
    code: str
    # Rend explicite l'intention (BUILD_PLAN.md §4) : `request-otp` reste
    # aveugle (toujours 204, non énumérant) précisément parce que la
    # décision compte/rôle n'a lieu qu'ici, après preuve de possession du
    # numéro (code OTP vérifié). `role` n'a de sens qu'en signup ; validé
    # explicitement contre une allow-list côté service (jamais `admin`),
    # pas seulement via ce type -- défense en profondeur, greppable et testée.
    intent: Literal["login", "signup"]
    role: Literal["client", "artisan"] | None = None
    # Requis en signup uniquement (revalidé côté service, comme `role` --
    # même raison : la présence/les bornes dépendent de `intent`, qu'un
    # simple `Field(...)` sur ce schéma ne peut pas exprimer). Ignoré en
    # login : un compte existant garde son nom (fix confidentialité du
    # contact -- avant ce correctif, un compte se créait avec le téléphone
    # comme nom, BUILD_PLAN.md).
    full_name: str | None = None


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
    # `None` si l'utilisateur n'a pas de profil artisan (client, ou artisan
    # sans profil créé) -- ferme le lien user <-> artisan_profile jamais
    # exposé jusqu'ici (AUDIT_PHASE2.md §6, BUILD_PLAN.md §6 Lot 12).
    artisan_profile_id: uuid.UUID | None


class TokenPairOut(BaseModel):
    access: str
    refresh: str


class AuthResponseOut(TokenPairOut):
    user: UserOut
