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

    # Longueur du code OTP (chiffres). 6 est le standard de l'industrie
    # (SMS, apps bancaires) : assez d'entropie combiné au TTL court et au
    # compteur d'attempts, assez court pour être saisi facilement.
    otp_code_length: int = 6
    # TTL du code OTP, en secondes. Défaut 5 min (BUILD_PLAN.md §4).
    otp_ttl_seconds: int = 300
    # Tentatives de vérification autorisées avant invalidation du code.
    otp_max_attempts: int = 5
    # Itérations PBKDF2-HMAC-SHA256 pour le hachage du code OTP. Un code à 6
    # chiffres n'a que 10^6 combinaisons : un hachage rapide (SHA-256 seul)
    # rendrait une fuite de la table `otp_code` triviale à bruteforcer hors
    # ligne. 600 000 est la recommandation OWASP (2023) pour PBKDF2-SHA256.
    otp_hash_iterations: int = 600_000

    # Secret de signature des JWT. Obligatoire, sans valeur par défaut :
    # même principe fail-fast que DATABASE_URL (Lot 6). Générer une valeur
    # avec `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
    # L'algorithme (HS256) n'est volontairement pas configurable via env --
    # le rendre configurable ouvrirait une attaque par confusion d'algorithme.
    jwt_secret: str
    # Durée de vie de l'access token, en secondes. Défaut 15 min : court,
    # car il n'est jamais révocable individuellement (JWT stateless).
    jwt_access_ttl_seconds: int = 900
    # Durée de vie du refresh token, en secondes. Défaut 30 jours : long,
    # car révocable (table refresh_token) et soumis à rotation.
    jwt_refresh_ttl_seconds: int = 2_592_000

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if not v.strip():
            raise ValueError(
                "JWT_SECRET est vide. Renseignez une valeur forte dans backend/.env "
                "(voir backend/.env.example) — aucune valeur par défaut n'est utilisée "
                "pour la signature des JWT."
            )
        if len(v) < 32:
            raise ValueError(
                f"JWT_SECRET est trop court ({len(v)} caractères, minimum 32) pour signer "
                "des JWT en sécurité. Générez une valeur aléatoire, ex. via "
                '`python -c "import secrets; print(secrets.token_urlsafe(48))"`.'
            )
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
