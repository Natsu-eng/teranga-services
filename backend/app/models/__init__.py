"""Modèles ORM SQLAlchemy, un module par domaine métier.

Importer ce paquet peuple `Base.metadata` de toutes les tables — c'est ce
qu'Alembic (`migrations/env.py`) importe pour l'autogenerate.
"""

from app.db.base import Base
from app.models.artisan import ArtisanProfile, ArtisanTrade, Verification
from app.models.audit import AuditLog
from app.models.commission import CommissionRate
from app.models.intervention import Intervention, InterventionDispute, Quote
from app.models.messaging import Conversation, Message
from app.models.otp import OtpCode
from app.models.payment import Payment, PaymentEvent, Payout, PlatformFee
from app.models.rate_limit import RateLimitHit
from app.models.refresh_token import RefreshToken
from app.models.request import ServiceRequest
from app.models.review import Review
from app.models.trade import Trade
from app.models.user import User

__all__ = [
    "ArtisanProfile",
    "ArtisanTrade",
    "AuditLog",
    "Base",
    "CommissionRate",
    "Conversation",
    "Intervention",
    "InterventionDispute",
    "Message",
    "OtpCode",
    "Payment",
    "PaymentEvent",
    "PlatformFee",
    "Payout",
    "Quote",
    "RateLimitHit",
    "RefreshToken",
    "Review",
    "ServiceRequest",
    "Trade",
    "User",
    "Verification",
]
