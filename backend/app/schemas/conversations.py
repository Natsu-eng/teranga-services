"""Schémas Pydantic de la messagerie (`/api/v1/conversations`, BUILD_PLAN.md
§3.2, Messagerie).

Aucun champ de contact n'est jamais exposé : l'interlocuteur n'est connu que
par son nom public (`app.services.identity.public_display_name`, qui masque
un nom resté au numéro de téléphone) et, pour un artisan, sa photo publique.
Le texte d'un message est TOUJOURS sa version masquée (numéros, e-mails).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import InterventionStatus, Role


class MessageCreateIn(BaseModel):
    # Bornes de longueur appliquées par le service (réglage
    # MESSAGING_BODY_MAX_LENGTH, après retrait des espaces superflus) : un
    # plafond large ici protège seulement d'un corps de requête démesuré.
    body: str = Field(max_length=20_000)


class MessageOut(BaseModel):
    """Message tel que délivré aux DEUX participants (REST et WebSocket) :
    aucune donnée propre à celui qui le lit."""

    id: uuid.UUID
    conversation_id: uuid.UUID
    seq: int
    sender_id: uuid.UUID
    body: str
    # Vrai si des coordonnées ont été masquées dans ce message : le front
    # affiche alors l'avertissement de transparence.
    contact_masked: bool
    # Image jointe : jamais d'URL publique, uniquement un indicateur ; le
    # contenu se lit par l'endpoint authentifié .../messages/{id}/attachment.
    has_attachment: bool
    attachment_content_type: str | None
    created_at: datetime


class MessageHistoryOut(BaseModel):
    """Page d'historique, toujours triée du plus ancien au plus récent.

    `has_more` : il existe des messages plus ANCIENS que le premier de la
    page (paramètre `before`). Sans objet pour `since` (toujours False).
    """

    items: list[MessageOut]
    has_more: bool


class ParticipantOut(BaseModel):
    user_id: uuid.UUID
    role: Role
    display_name: str
    # Photo publique de l'artisan ; toujours nulle pour un client.
    avatar_url: str | None
    # Profil artisan (lien vers la fiche publique) ; nul pour un client.
    artisan_profile_id: uuid.UUID | None


class LastMessagePreviewOut(BaseModel):
    body: str
    from_me: bool
    has_attachment: bool
    created_at: datetime


class ConversationSummaryOut(BaseModel):
    """Ligne de la liste « Messages » (propre à l'utilisateur courant)."""

    id: uuid.UUID
    intervention_id: uuid.UUID | None
    intervention_status: InterventionStatus | None
    trade_label: str | None
    other_party: ParticipantOut
    last_message: LastMessagePreviewOut | None
    unread_count: int
    last_activity_at: datetime


class ConversationOut(BaseModel):
    """Métadonnées d'un fil, pour l'en-tête de l'écran de discussion."""

    id: uuid.UUID
    intervention_id: uuid.UUID | None
    intervention_status: InterventionStatus | None
    trade_label: str | None
    other_party: ParticipantOut
    # Curseur de lecture de l'utilisateur courant (séparateur « non lus »).
    my_last_read_seq: int
    # Faux si l'intervention a été refusée : le fil reste lisible, mais
    # n'accepte plus de nouveaux messages.
    can_send: bool
    created_at: datetime


class MarkReadIn(BaseModel):
    # `seq` du dernier message vu ; le curseur ne recule jamais.
    last_read_seq: int = Field(ge=0)


class UnreadCountOut(BaseModel):
    count: int


class WsTicketOut(BaseModel):
    ticket: str
    expires_in: int
