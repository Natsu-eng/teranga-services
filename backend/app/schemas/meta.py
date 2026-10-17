"""Schéma de `GET /api/v1/meta` : informations publiques sur l'instance."""

from pydantic import BaseModel

from app.core.config import Environment


class MetaOut(BaseModel):
    # Environnement de l'instance : le front affiche le bandeau « Version de
    # test » partout sauf en production.
    environment: Environment
    # Vrai si des numéros de test se connectent sans SMS (staging seulement).
    # Un simple booléen : la liste des numéros et le code ne sortent JAMAIS.
    otp_test_mode: bool
