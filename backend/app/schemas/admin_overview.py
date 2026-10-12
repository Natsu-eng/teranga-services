"""Vue d'ensemble du back-office (`GET /admin/overview`).

Chaque chiffre est DÉRIVÉ des tables métier, jamais saisi ni estimé : la
docstring de chaque champ dit d'où il vient. Sans données, des zéros — jamais
un chiffre inventé. Montants en FCFA entiers.
"""

from datetime import datetime

from pydantic import BaseModel


class ArtisanCountsOut(BaseModel):
    # `artisan_profile` non supprimés, par statut de vérification stocké.
    total: int
    none: int
    pending: int
    verified: int
    rejected: int
    # Suspendus par un admin (quel que soit leur statut de vérification).
    suspended: int


class UserCountsOut(BaseModel):
    # `user` non supprimés, par rôle.
    clients: int
    artisans: int
    admins: int


class InterventionCountsOut(BaseModel):
    # `intervention`, par statut.
    proposee: int
    acceptee: int
    en_cours: int
    terminee: int
    annulee: int
    litige: int


class MoneyOut(BaseModel):
    # Somme de `payment.amount_fcfa` par statut.
    in_escrow_fcfa: int  # `retenu` : chez Téranga, en attente de la fin des travaux
    released_fcfa: int  # `libere` : séquestre versé à l'artisan
    cash_fcfa: int  # `reussi` : espèces réglées directement à l'artisan
    refunded_fcfa: int  # `rembourse` : rendu au client
    # Volume d'affaires = séquestre + libéré + espèces (l'argent qui a
    # réellement circulé, remboursements exclus).
    business_volume_fcfa: int
    # Somme de `platform_fee.amount_fcfa` (commissions) :
    commission_collected_fcfa: int  # `collectee` : prélevée à la libération
    commission_due_fcfa: int  # `due` sur travaux terminés : due par l'artisan (cash)
    commission_pending_fcfa: int  # `due` sur travaux en cours : prélevée à la libération


class AdminOverviewOut(BaseModel):
    artisans: ArtisanCountsOut
    users: UserCountsOut
    interventions: InterventionCountsOut
    money: MoneyOut
    # `verification` au statut `pending` (documents à examiner).
    pending_verifications: int
    # `intervention_dispute` non tranchés sur une intervention en litige.
    open_disputes: int
    generated_at: datetime
