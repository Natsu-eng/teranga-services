"""Grille de commission administrée (`/admin/commission-rates`, BUILD_PLAN.md §3.6).

Taux en points de base (`rate_bps`) : 1000 = 10 %. Un taux ne se modifie ni
ne se supprime : on en ajoute un nouveau, daté.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.models.enums import SubscriptionTier


class AdminCommissionRateOut(BaseModel):
    id: uuid.UUID
    rate_bps: int
    # `trade_*` nuls : taux global (tous métiers sans taux propre).
    trade_id: uuid.UUID | None
    trade_code: str | None
    trade_label: str | None
    tier: SubscriptionTier | None
    effective_from: datetime
    effective_to: datetime | None
    # Dérivé de l'heure courante : en vigueur, programmé (futur) ou archivé.
    state: Literal["en_vigueur", "programme", "archive"]
    # Interventions qui ont FIGÉ ce taux à leur création.
    interventions_count: int
    created_at: datetime


class CommissionGridOut(BaseModel):
    items: list[AdminCommissionRateOut]
    # Plafond de saisie configuré (COMMISSION_RATE_MAX_BPS), affiché par
    # l'interface comme garde-fou avant l'envoi.
    max_rate_bps: int
    generated_at: datetime


class CommissionRateCreateIn(BaseModel):
    rate_bps: int = Field(ge=0, le=10_000)
    # Absent : taux global. Sinon, le code d'un métier du catalogue.
    trade_code: str | None = Field(default=None, min_length=1, max_length=50)
    # Accepté au schéma pour répondre clairement 422 PALIER_NON_APPLIQUE.
    tier: SubscriptionTier | None = None
    # Absent : maintenant. Fuseau horaire obligatoire, jamais dans le passé.
    effective_from: AwareDatetime | None = None
    note: str | None = Field(default=None, max_length=1000)
