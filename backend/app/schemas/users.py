"""Schémas Pydantic de `/api/v1/users` (BUILD_PLAN.md, fix confidentialité
du contact) -- édition du compte, rôle-agnostique (client ou artisan)."""

from pydantic import BaseModel


class UserProfileUpdateIn(BaseModel):
    full_name: str
