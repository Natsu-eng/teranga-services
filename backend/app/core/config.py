from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    app_env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    # "console" (dev, log lisible) est le seul fournisseur implémenté à ce
    # stade -- un fournisseur SMS commercial reste à choisir avant la prod
    # (BUILD_PLAN.md §4). "unconfigured" échoue explicitement à l'envoi,
    # pour ne jamais retomber silencieusement sur le provider console hors dev.
    sms_provider: Literal["console", "unconfigured"] = "console"

    # Région par défaut pour interpréter un numéro écrit sans indicatif
    # (ex. "771234567" -> Sénégal). Code région ISO 3166-1 alpha-2 attendu
    # par `phonenumbers`. Configurable pour préparer l'internationalisation
    # (BUILD_PLAN.md §4.1) sans toucher au code.
    phone_default_region: str = "SN"
    # Régions dont les numéros sont acceptés -- un numéro valide mais d'une
    # région absente de cette liste est explicitement rejeté (on ne veut pas
    # créer de comptes avec des numéros qu'on ne sait pas encore servir).
    phone_allowed_regions: Annotated[list[str], NoDecode] = ["SN"]

    @field_validator("phone_allowed_regions", mode="before")
    @classmethod
    def split_phone_allowed_regions(cls, v: object) -> object:
        if isinstance(v, str):
            return [region.strip().upper() for region in v.split(",") if region.strip()]
        return v

    # NoDecode : sans ça, pydantic-settings tente de parser la valeur brute
    # de l'env en JSON avant même d'atteindre le validator ci-dessous, ce qui
    # échoue pour une liste séparée par des virgules comme CORS_ORIGINS.
    cors_origins: Annotated[list[str], NoDecode] = []

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, v: object) -> object:
        # Permet CORS_ORIGINS=http://a,http://b dans .env plutôt que du JSON.
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "DATABASE_URL est vide. Renseignez-la dans backend/.env "
                "(voir backend/.env.example) — aucune base par défaut n'est utilisée."
            )
        try:
            url = make_url(v)
        except ArgumentError as exc:
            raise ValueError(
                f"DATABASE_URL est malformée ({exc}). Format attendu : "
                "postgresql+asyncpg://user:password@host:port/dbname"
            ) from exc
        if url.drivername != "postgresql+asyncpg":
            raise ValueError(
                "DATABASE_URL doit utiliser le driver asyncpg pour SQLAlchemy async "
                f"(postgresql+asyncpg://...) — reçu : {url.drivername}://..."
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
