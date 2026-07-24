"""Modèles ORM SQLAlchemy, un module par domaine métier.

Importer ce paquet peuple `Base.metadata` de toutes les tables — c'est ce
qu'Alembic (`migrations/env.py`) importe pour l'autogenerate.
"""

from app.db.base import Base
from app.models.artisan import ArtisanProfile, ArtisanTrade, Verification
from app.models.commission import CommissionRate
from app.models.intervention import Intervention, Quote
from app.models.messaging import Conversation, Message
from app.models.otp import OtpCode
from app.models.payment import Payment, Payout, PlatformFee
from app.models.request import ServiceRequest
from app.models.review import Review
from app.models.trade import Trade
from app.models.user import User

__all__ = [
    "ArtisanProfile",
    "ArtisanTrade",
    "Base",
    "CommissionRate",
    "Conversation",
    "Intervention",
    "Message",
    "OtpCode",
    "Payment",
    "PlatformFee",
    "Payout",
    "Quote",
    "Review",
    "ServiceRequest",
    "Trade",
    "User",
    "Verification",
]
