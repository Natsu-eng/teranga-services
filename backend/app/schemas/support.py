"""Schémas des demandes d'aide (`/api/v1/support`, `/api/v1/admin/support`).

Entrées BORNÉES ici (protection contre un corps démesuré) ; le contenu est
ensuite masqué par le service (numéros, e-mails). Le message renvoyé est
toujours la version masquée.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import Role, SupportCategory, SupportTicketStatus
from app.models.support import (
    SUPPORT_MESSAGE_MAX_LENGTH,
    SUPPORT_MESSAGE_MIN_LENGTH,
    SUPPORT_REPLY_MAX_LENGTH,
    SUPPORT_REPLY_MIN_LENGTH,
)


class SupportTicketCreateIn(BaseModel):
    category: SupportCategory
    message: str = Field(
        min_length=SUPPORT_MESSAGE_MIN_LENGTH, max_length=SUPPORT_MESSAGE_MAX_LENGTH
    )
    # Facultatif : intervention concernée, appartenant obligatoirement à l'auteur.
    intervention_id: uuid.UUID | None = None


class SupportTicketOut(BaseModel):
    """Une demande, vue par son AUTEUR (aucune donnée d'un tiers)."""

    id: uuid.UUID
    category: SupportCategory
    message: str
    intervention_id: uuid.UUID | None
    # Métier de l'intervention liée (repère lisible), sinon null.
    intervention_trade_label: str | None
    status: SupportTicketStatus
    admin_reply: str | None
    replied_at: datetime | None
    resolved_at: datetime | None
    created_at: datetime


class AdminSupportTicketOut(SupportTicketOut):
    """Une demande, vue par un admin : qui l'a envoyée (nom public et rôle,
    jamais le numéro de téléphone)."""

    author_id: uuid.UUID
    author_name: str
    author_role: Role


class SupportReplyIn(BaseModel):
    reply: str = Field(min_length=SUPPORT_REPLY_MIN_LENGTH, max_length=SUPPORT_REPLY_MAX_LENGTH)
    # Vrai (défaut) : la demande est close avec cette réponse. Faux : réponse
    # d'attente (demande de précision), la demande reste ouverte.
    resolve: bool = True
