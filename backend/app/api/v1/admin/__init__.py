"""Endpoints /api/v1/admin (BUILD_PLAN.md §3.6, back-office).

Toutes les routes exigent le rôle admin (`require_role(Role.ADMIN)`, même
dépendance que le reste de l'API, Lot 8), relu en base à chaque requête :
un retrait de rôle coupe l'accès immédiatement. Un client/artisan reçoit 403
ROLE_INSUFFISANT, un anonyme 401 NON_AUTHENTIFIE -- exactement les mêmes
erreurs génériques que n'importe quelle autre route protégée par rôle, sans
détail qui distinguerait une route admin d'une autre pour un tiers.

Le PREMIER admin naît uniquement du script `scripts/create_admin.py` ;
ensuite, un admin peut promouvoir/retirer d'autres comptes
(`/admin/users/...`), sous garde anti-verrouillage. Chaque action sensible
est inscrite au journal d'audit en ajout seul (`GET /admin/audit`).

Une section par module (même préfixe `/admin`, même tag, mêmes chemins et
mêmes noms de routes, donc mêmes operationId OpenAPI qu'avant la découpe).
"""

from fastapi import APIRouter

from app.api.v1.admin import (
    artisans,
    audit,
    commissions,
    diagnostics,
    disputes,
    overview,
    reviews,
    support,
    users,
    verifications,
)

router = APIRouter(prefix="/admin", tags=["admin"])
# Ordre d'inclusion = ordre des routes dans l'ancien module unique.
for section in (verifications, artisans, disputes, audit, overview, users, reviews, commissions):
    router.include_router(section.router)
# Diagnostic d'exploitation (réglage des proxys), ajouté après la découpe.
router.include_router(diagnostics.router)
# Aide : file des demandes d'aide (lot feat/disputes-support).
router.include_router(support.router)
