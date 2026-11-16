import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Bornes de saisie (vérifiées par le schéma d'entrée) : une adresse
# d'abonnement réelle fait quelques centaines de caractères ; les clés sont
# de taille fixe en base64url (65 et 16 octets).
PUSH_ENDPOINT_MAX_LENGTH = 2048
PUSH_P256DH_MAX_LENGTH = 128
PUSH_AUTH_MAX_LENGTH = 64


class PushSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Abonnement Web Push d'UN appareil (navigateur ou application
    installée) d'un utilisateur. Un compte peut en avoir plusieurs.

    - `endpoint` : adresse fournie par le service de push du navigateur
      (FCM, Mozilla, Apple, Windows). UNIQUE : un même navigateur n'appartient
      qu'à un compte à la fois -- s'il change de compte, l'abonnement passe au
      nouveau (jamais de notification de l'ancien compte sur un appareil
      partagé).
    - `p256dh`, `auth` : clés publiques du navigateur, qui chiffrent le
      contenu de bout en bout (RFC 8291) ; le service de push ne peut pas
      le lire.

    `updated_at` : dernier enregistrement par l'appareil (l'application
    le resynchronise à chaque ouverture) ; sert à oublier le plus ancien
    au-delà de WEB_PUSH_MAX_SUBSCRIPTIONS_PER_USER. Supprimé avec le compte
    (CASCADE) ou dès que le service de push le déclare expiré (404/410).
    """

    __tablename__ = "push_subscription"
    __table_args__ = (
        # Défense en profondeur (le service vérifie déjà l'hôte autorisé) :
        # jamais d'adresse d'envoi en clair ni démesurée, même écrite à la main.
        CheckConstraint("endpoint LIKE 'https://%'", name="endpoint_https"),
        CheckConstraint(
            f"char_length(endpoint) <= {PUSH_ENDPOINT_MAX_LENGTH}", name="endpoint_max_length"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String(PUSH_P256DH_MAX_LENGTH), nullable=False)
    auth: Mapped[str] = mapped_column(String(PUSH_AUTH_MAX_LENGTH), nullable=False)
