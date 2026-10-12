"""Adresse IP réelle du client, derrière un ou plusieurs proxys de confiance
(DEPLOYMENT.md).

En production, le backend est derrière le proxy de la plateforme (Railway) :
`request.client.host` y est l'adresse DU PROXY, la même pour tout le monde.
Utilisée telle quelle par le rate limiting par IP (OTP, triage IA), elle
mettrait toute la plateforme dans un seul compteur -- quelques demandes
suffiraient à bloquer tous les utilisateurs.

`X-Forwarded-For` liste les adresses traversées, chaque proxy AJOUTANT à
droite celle qu'il a vue. Seules les entrées ajoutées par NOS proxys sont
fiables : tout ce qui est à leur gauche peut avoir été écrit par le client
lui-même. Avec `TRUSTED_PROXY_HOPS = n`, on lit donc la n-ième entrée en
partant de la droite -- jamais la plus à gauche (falsifiable : un attaquant
contournerait la limite en changeant d'en-tête à chaque requête).

`TRUSTED_PROXY_HOPS=0` (défaut, dev) : aucun proxy, l'en-tête est ignoré.
"""

from fastapi import Request

from app.core.config import Settings


def client_ip(request: Request, settings: Settings) -> str:
    direct = request.client.host if request.client else "unknown"
    hops = settings.trusted_proxy_hops or 0
    if hops <= 0:
        return direct
    forwarded = [
        part.strip()
        for header in request.headers.getlist("x-forwarded-for")
        for part in header.split(",")
        if part.strip()
    ]
    if len(forwarded) < hops:
        # En-tête absent ou plus court que la chaîne de proxys attendue :
        # requête qui n'est pas passée par eux (accès interne, sonde).
        return direct
    return forwarded[-hops]
