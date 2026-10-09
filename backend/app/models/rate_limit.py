from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Identity, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RateLimitHit(Base):
    """Un appel décompté par le rate limiting partagé
    (`app.services.rate_limit.PostgresRateLimiter`).

    Remplace l'état en mémoire par processus pour les déploiements à
    plusieurs instances : la limite est la même quel que soit le nombre de
    workers, et survit à un redémarrage. Ne stocke JAMAIS la clé en clair
    (numéro de téléphone, IP, identifiant utilisateur) : seulement son
    empreinte SHA-256 (`key_hash`), suffisante pour compter les appels --
    une fuite de cette table ne révèle ni qui s'est connecté ni d'où.

    Clé primaire entière (pas un UUID comme les tables métier) : table à fort
    volume, purement technique, jamais exposée par l'API.
    """

    __tablename__ = "rate_limit_hit"
    __table_args__ = (
        # Sert la seule requête chaude : compter les appels d'une clé dans la
        # fenêtre (et purger les siens au passage).
        Index("ix_rate_limit_hit_bucket_key_hash_hit_at", "bucket", "key_hash", "hit_at"),
        # Sert la purge globale des lignes expirées.
        Index("ix_rate_limit_hit_hit_at", "hit_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Limiteur d'origine ("otp", "ai_analyze", ...) : deux fonctionnalités
    # ne partagent jamais un compteur, même pour une même IP.
    bucket: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Horloge de la BASE (clock_timestamp), jamais celle d'une instance :
    # deux instances aux horloges décalées comptent sur la même référence.
    hit_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("clock_timestamp()")
    )
