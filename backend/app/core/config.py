import re
from functools import lru_cache
from typing import Annotated, Literal, get_args

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.models.enums import PaymentChannel, PayoutChannel, VerificationDocType

# Environnements reconnus : ensemble FERMÉ. Toute autre valeur fait échouer
# le démarrage (une faute de frappe ne doit jamais faire tourner la prod
# avec les réglages permissifs du dev).
Environment = Literal["development", "test", "staging", "production"]
ENVIRONMENTS: tuple[str, ...] = get_args(Environment)
# Anciennes valeurs de APP_ENV, toujours acceptées (fichiers .env existants).
_LEGACY_ENVIRONMENTS = {"dev": "development", "prod": "production"}

# Fragments qui trahissent une valeur d'exemple jamais remplacée (copiée de
# .env.example ou d'une documentation) : refusée pour un secret en production.
_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "change_me",
    "placeholder",
    "replace-me",
    "remplacer",
    "example",
    "exemple",
    "your-",
    "votre-",
    "xxxx",
)
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})
# Numéro E.164 : « + », indicatif sans zéro initial, 8 à 15 chiffres au total.
_E164_RE = re.compile(r"\+[1-9]\d{7,14}")


def normalize_environment_name(raw: str) -> str:
    """Nom d'environnement normalisé (casse, anciennes valeurs dev/prod) ;
    lève `ValueError` hors de l'ensemble fermé, en citant les valeurs admises."""
    value = _LEGACY_ENVIRONMENTS.get(raw.strip().lower(), raw.strip().lower())
    if value not in ENVIRONMENTS:
        raise ValueError(
            f"ENVIRONMENT={raw!r} inconnu. Valeurs acceptées : {', '.join(ENVIRONMENTS)}."
        )
    return value


def looks_like_placeholder(value: str) -> bool:
    """Vrai pour une valeur d'exemple manifeste (« change-me », « exemple »...)."""
    lowered = value.strip().lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Les tests construisent Settings par nom de champ (`environment=`) ;
        # l'environnement réel passe par ENVIRONMENT (ou l'ancien APP_ENV).
        populate_by_name=True,
    )

    database_url: str
    # ENVIRONMENT : development (défaut), test, staging ou production.
    # APP_ENV reste accepté (ancien nom), avec ses anciennes valeurs dev/prod.
    environment: Environment = Field(
        default="development", validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV")
    )
    log_level: str = "INFO"

    @field_validator("environment", mode="before")
    @classmethod
    def normalize_environment(cls, v: object) -> object:
        return normalize_environment_name(v) if isinstance(v, str) else v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_local(self) -> bool:
        """Poste de développement ou suite de tests : seuls environnements où
        les replis permissifs (mémoire, console, sandbox sans secret) sont
        admis."""
        return self.environment in ("development", "test")

    # "console" (dev, log lisible) est le seul fournisseur implémenté à ce
    # stade -- un fournisseur SMS commercial reste à choisir avant la prod
    # (BUILD_PLAN.md §4, DEPLOYMENT.md). "unconfigured" échoue explicitement
    # à l'envoi. En PRODUCTION, les deux sont refusés au démarrage
    # (`validate_production`) : une prod où personne ne peut recevoir son
    # code de connexion ne doit jamais démarrer.
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

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, v: list[str]) -> list[str]:
        for origin in v:
            if "*" in origin:
                raise ValueError(
                    "CORS_ORIGINS ne doit jamais contenir de joker « * » : listez les origines "
                    "exactes du front (les jetons d'accès transitent par ces appels)."
                )
            # Une origine = schéma + hôte (+ port), rien d'autre : le
            # navigateur compare à l'identique, un « / » final ou un chemin
            # ne correspondrait jamais (CORS cassé sans message clair).
            if _origin_of(origin) != origin:
                raise ValueError(
                    f"CORS_ORIGINS : {origin!r} n'est pas une origine (attendu : "
                    "https://hote[:port], sans chemin ni « / » final)."
                )
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

    # --- Mode OTP de TEST (beta, DEPLOYMENT.md) ---------------------------
    # Permis UNIQUEMENT avec ENVIRONMENT=staging (refusé au démarrage
    # partout ailleurs, production comprise). Pour un numéro de la liste,
    # `request-otp` ne passe pas par le fournisseur SMS : le code émis est
    # OTP_TEST_CODE. Seule la LIVRAISON change : le code est haché, à usage
    # unique, expirant, limité en tentatives et en débit, exactement comme un
    # code normal. Les numéros hors liste suivent le flux normal.
    # Numéros E.164 (ex. +221770000001), séparés par des virgules.
    otp_test_whitelist: Annotated[list[str], NoDecode] = []
    # Code de test : exactement OTP_CODE_LENGTH chiffres. Aucune valeur par
    # défaut (jamais un code en dur) ; obligatoire si la liste est remplie.
    otp_test_code: str | None = None

    @field_validator("otp_test_whitelist", mode="before")
    @classmethod
    def split_otp_test_whitelist(cls, v: object) -> object:
        if isinstance(v, str):
            return [number.strip() for number in v.split(",") if number.strip()]
        return v

    @field_validator("otp_test_whitelist")
    @classmethod
    def validate_otp_test_whitelist(cls, v: list[str]) -> list[str]:
        for number in v:
            if not _E164_RE.fullmatch(number):
                raise ValueError(
                    f"OTP_TEST_WHITELIST : {number!r} n'est pas un numéro E.164 "
                    "(ex. +221770000001)."
                )
        return v

    @field_validator("otp_test_code", mode="before")
    @classmethod
    def empty_otp_test_code_means_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def validate_otp_test_mode(self) -> "Settings":
        configured = bool(self.otp_test_whitelist) or self.otp_test_code is not None
        # Production : refusé par `validate_production`, avec la liste complète
        # de ses autres problèmes. Ici, tout autre environnement que staging.
        if not configured or self.environment == "production":
            return self
        if self.environment != "staging":
            raise ValueError(
                f"OTP_TEST_WHITELIST / OTP_TEST_CODE ne sont permis qu'avec ENVIRONMENT=staging "
                f"(reçu {self.environment})."
            )
        if not self.otp_test_whitelist or self.otp_test_code is None:
            raise ValueError(
                "Mode OTP de test incomplet : OTP_TEST_WHITELIST et OTP_TEST_CODE vont ensemble."
            )
        if not (
            self.otp_test_code.isascii()
            and self.otp_test_code.isdigit()
            and len(self.otp_test_code) == self.otp_code_length
        ):
            raise ValueError(
                f"OTP_TEST_CODE doit compter exactement {self.otp_code_length} chiffres."
            )
        return self

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

    # Redis partagé (DEPLOYMENT.md). Renseigné : le rate limiting, la
    # diffusion temps réel de la messagerie et l'usage unique des tickets
    # WebSocket passent par Redis -- état commun à toutes les instances.
    # Vide (dev) : repli automatique sur l'existant (mémoire du processus ;
    # PostgreSQL pour le rate limiting hors development/test). Indispensable
    # dès que le backend tourne sur plus d'une instance.
    redis_url: str | None = None

    @field_validator("redis_url", mode="before")
    @classmethod
    def empty_redis_url_means_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("redis://", "rediss://", "unix://")):
            raise ValueError("REDIS_URL doit commencer par redis://, rediss:// ou unix://.")
        return v

    # Stockage des compteurs de TOUS les rate limitings (OTP, triage IA,
    # documents, médias de profil) -- voir app/services/rate_limit.py.
    # - "redis" : partagé par toutes les instances, rapide (exige REDIS_URL) ;
    # - "postgres" : table `rate_limit_hit`, partagée par toutes les
    #   instances et persistante (survit à un redémarrage/déploiement) ;
    # - "memory" : état local au processus, pour le dev et les tests.
    # Non renseigné : "redis" si REDIS_URL est renseignée, sinon "memory" en
    # development/test et "postgres" en staging/production. "memory"
    # explicitement demandé en staging/production est REFUSÉ au démarrage
    # (`validate_rate_limit_backend`) : derrière plusieurs instances, chacune
    # appliquerait sa propre limite (limite réelle multipliée d'autant), et
    # chaque redéploiement remettrait tous les compteurs à zéro.
    rate_limit_backend: Literal["memory", "postgres", "redis"] | None = None

    @field_validator("rate_limit_backend", mode="before")
    @classmethod
    def empty_rate_limit_backend_means_auto(cls, v: object) -> object:
        # `RATE_LIMIT_BACKEND=` (vide, la valeur recommandée de .env.example)
        # signifie « choix automatique », pas une valeur invalide.
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def validate_rate_limit_backend(self) -> "Settings":
        if self.rate_limit_backend is None:
            if self.redis_url:
                self.rate_limit_backend = "redis"
            else:
                self.rate_limit_backend = "memory" if self.is_local else "postgres"
        elif self.rate_limit_backend == "redis" and not self.redis_url:
            raise ValueError("RATE_LIMIT_BACKEND=redis exige REDIS_URL.")
        elif self.rate_limit_backend == "memory" and not self.is_local:
            raise ValueError(
                f"RATE_LIMIT_BACKEND=memory est interdit avec ENVIRONMENT={self.environment} : "
                "les limites ne seraient ni partagées entre instances ni conservées au "
                "redémarrage. Utilisez RATE_LIMIT_BACKEND=postgres (ou laissez-la vide)."
            )
        return self

    # Nombre de proxys de confiance devant le backend (app/core/client_ip.py).
    # 0 : accès direct (dev) -- l'IP du client est celle de la connexion.
    # Railway (un proxy de bordure) : 1. Indispensable au rate limiting par
    # IP : sans lui, derrière un proxy, tous les clients partageraient l'IP
    # du proxy. Doit être renseigné EXPLICITEMENT en production.
    trusted_proxy_hops: int | None = Field(default=None, ge=0, le=5)

    @field_validator("trusted_proxy_hops", mode="before")
    @classmethod
    def empty_trusted_proxy_hops_means_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # Rate limiting sur /auth/request-otp, fenêtre glissante (stockage selon
    # RATE_LIMIT_BACKEND ci-dessus).
    rate_limit_otp_per_phone_max: int = 3
    rate_limit_otp_per_phone_window_seconds: int = 600
    rate_limit_otp_per_ip_max: int = 10
    rate_limit_otp_per_ip_window_seconds: int = 600

    # Rayon de recherche par défaut si le client ne précise pas `radius_m` sur
    # GET /artisans, en mètres. 10 km couvre la quasi-totalité du Grand Dakar
    # depuis un point central (Plateau -> Almadies ~9,3 km, cf. tests/test_geo.py).
    artisan_search_default_radius_m: int = 10_000
    # Plafond dur du rayon de recherche, en mètres -- au-delà, une recherche
    # perd sa pertinence géo et dégrade la sélectivité de l'index GiST.
    artisan_search_max_radius_m: int = 50_000

    # Pagination offset bornée (BUILD_PLAN.md §6, Lot 9), réutilisée par
    # GET /artisans et GET /artisans/{id}/reviews.
    pagination_page_size_default: int = 20
    pagination_page_size_max: int = 50
    # Page maximale autorisée -- au-delà, rejet 422 explicite (PAGE_HORS_BORNES),
    # jamais un clamp silencieux. À page_size max, plafonne l'offset scanné à
    # 2 450 lignes -- large pour un marché artisan filtré par rayon géo.
    pagination_max_page: int = 50

    # Types de documents requis pour verified_status=VERIFIED (voir
    # app.services.verification.compute_verified_status). CNI + selfie :
    # preuve d'identité + preuve que la personne qui a soumis la CNI en est
    # bien la titulaire -- le socle KYC minimal, avant une éventuelle
    # accréditation métier (pas encore exigée par défaut).
    verification_required_doc_types: Annotated[list[VerificationDocType], NoDecode] = [
        VerificationDocType.CNI,
        VerificationDocType.SELFIE,
    ]

    @field_validator("verification_required_doc_types", mode="before")
    @classmethod
    def split_verification_required_doc_types(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    # Fournisseur actif pour POST /api/v1/ai/analyze (BUILD_PLAN.md §3.2, §6
    # Lot 11). "heuristique" (filet par mots-clés, sans appel réseau, sans
    # coût, sans clé) est le défaut sûr -- même principe fail-closed que
    # `sms_provider` (défaut "console") : un déploiement sans MISTRAL_API_KEY
    # renseignée continue de répondre. "mistral" active l'appel réseau réel ;
    # à la moindre anomalie (timeout, erreur API, JSON non conforme, métier
    # inconnu), le service retombe automatiquement sur l'heuristique --
    # jamais d'erreur 500 pour un incident IA (voir app/services/ai_triage.py).
    ai_triage_provider: Literal["mistral", "heuristic"] = "heuristic"
    # Jamais de valeur par défaut : une clé en dur dans le code serait un
    # secret commité. Absente, `MistralTriageProvider` échoue proprement
    # (fallback heuristique) sans jamais tenter l'appel réseau.
    mistral_api_key: str | None = None
    # Modèle économique par défaut (gamme "small") -- configurable sans
    # toucher au code si un modèle plus ou moins coûteux devient préférable.
    mistral_model: str = "mistral-small-latest"
    mistral_api_base_url: str = "https://api.mistral.ai/v1"
    # Timeout explicite sur l'appel Mistral, en secondes -- un appel IA ne
    # doit jamais faire attendre indéfiniment une requête client ; au-delà,
    # bascule sur l'heuristique.
    mistral_timeout_seconds: float = 10.0

    # Rate limiting sur POST /api/v1/ai/analyze, même mécanisme (fenêtre
    # glissante, stockage RATE_LIMIT_BACKEND) que RATE_LIMIT_OTP_* -- voir
    # app/services/rate_limit.py. Par IP uniquement : l'endpoint est public,
    # non authentifié (l'écran /demande ne requiert pas de connexion), donc
    # aucune identité utilisateur fiable à clé dessus. Chaque appel coûte
    # potentiellement de l'argent réel (fournisseur réseau) : la limite
    # protège le provider actif même quand le fallback heuristique (gratuit)
    # finit par répondre.
    rate_limit_ai_analyze_per_ip_max: int = 20
    rate_limit_ai_analyze_per_ip_window_seconds: int = 600

    # Stockage des fichiers privés (documents de vérification artisan --
    # onboarding). "local" (dev) écrit sur disque hors du dépôt git et hors
    # de tout répertoire servi statiquement -- voir app/services/storage.py.
    # "s3" : stockage S3-compatible (AWS S3, Cloudflare R2...), bucket PRIVÉ
    # (app/services/s3_storage.py). C'est aussi la valeur par défaut des
    # deux autres stockages (avatars, pièces jointes) s'ils ne sont pas
    # précisés. En production, "local" est REFUSÉ : le disque d'un service
    # Railway est éphémère, les fichiers seraient perdus au redéploiement.
    storage_backend: Literal["local", "s3"] = "local"
    # Chemin (relatif au dossier backend/, ou absolu) du répertoire de
    # stockage local. Défaut "var/artisan-documents" : hors du code source
    # applicatif, ignoré par backend/.gitignore, jamais monté en StaticFiles
    # (app/main.py ne sert aucun fichier statique). Pour une isolation plus
    # stricte encore (répertoire littéralement hors du dépôt), fournir un
    # chemin absolu via cette variable.
    storage_local_dir: str = "var/artisan-documents"
    # Taille maximale d'un document uploadé, en octets. Défaut 8 Mo : large
    # pour une photo de CNI/selfie prise au téléphone, sans autoriser des
    # fichiers déraisonnables qui gonfleraient le stockage local et le temps
    # de traitement (magic bytes, écriture disque).
    storage_max_upload_bytes: int = 8 * 1024 * 1024

    # --- Stockage S3-compatible (STORAGE_BACKEND=s3, DEPLOYMENT.md) --------
    # Point d'accès : vide pour AWS S3 ; pour Cloudflare R2,
    # https://<ACCOUNT_ID>.r2.cloudflarestorage.com.
    s3_endpoint_url: str | None = None
    # Région : "auto" pour R2, la région du bucket pour AWS (ex. eu-west-3).
    s3_region: str = "auto"
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    # Bucket PRIVÉ (aucun accès public) : documents d'identité et pièces
    # jointes, toujours servis par les endpoints authentifiés.
    s3_private_bucket: str | None = None
    # Bucket PUBLIC : photos de profil et couvertures seulement. Doit être
    # DIFFÉRENT du bucket privé (refusé au démarrage sinon).
    s3_public_bucket: str | None = None
    # URL publique du bucket public (domaine personnalisé R2/CDN ou URL
    # publique du bucket), en HTTPS : base des URL d'avatar renvoyées au front.
    s3_public_base_url: str | None = None

    @field_validator(
        "avatar_storage_backend",
        "message_attachment_storage_backend",
        "s3_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_private_bucket",
        "s3_public_bucket",
        "s3_public_base_url",
        mode="before",
    )
    @classmethod
    def empty_storage_value_means_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @model_validator(mode="after")
    def validate_storage(self) -> "Settings":
        # Stockages non précisés : même fournisseur que STORAGE_BACKEND.
        if self.avatar_storage_backend is None:
            self.avatar_storage_backend = self.storage_backend
        if self.message_attachment_storage_backend is None:
            self.message_attachment_storage_backend = self.storage_backend

        private_on_s3 = "s3" in (self.storage_backend, self.message_attachment_storage_backend)
        public_on_s3 = self.avatar_storage_backend == "s3"
        if not (private_on_s3 or public_on_s3):
            return self
        missing = [
            name
            for name, value, needed in (
                ("S3_ACCESS_KEY_ID", self.s3_access_key_id, True),
                ("S3_SECRET_ACCESS_KEY", self.s3_secret_access_key, True),
                ("S3_PRIVATE_BUCKET", self.s3_private_bucket, private_on_s3),
                ("S3_PUBLIC_BUCKET", self.s3_public_bucket, public_on_s3),
                ("S3_PUBLIC_BASE_URL", self.s3_public_base_url, public_on_s3),
            )
            if needed and not value
        ]
        if missing:
            raise ValueError(f"Stockage S3 incomplet, à renseigner : {', '.join(missing)}.")
        if self.s3_private_bucket and self.s3_private_bucket == self.s3_public_bucket:
            raise ValueError(
                "S3_PRIVATE_BUCKET et S3_PUBLIC_BUCKET doivent être deux buckets différents : "
                "un document d'identité ne doit jamais pouvoir se retrouver dans un bucket public."
            )
        if public_on_s3 and not (self.s3_public_base_url or "").startswith(("https://", "http://")):
            raise ValueError("S3_PUBLIC_BASE_URL doit être une URL http(s) absolue.")
        return self

    # Rate limiting sur POST /api/v1/artisans/me/documents, même mécanisme
    # (fenêtre glissante, stockage RATE_LIMIT_BACKEND) que RATE_LIMIT_OTP_*. Par utilisateur
    # authentifié (pas par IP : l'endpoint exige déjà un compte artisan) --
    # une écriture disque + un hachage de magic bytes par appel ne doivent
    # pas pouvoir être déclenchés en boucle.
    rate_limit_document_upload_per_user_max: int = 10
    rate_limit_document_upload_per_user_window_seconds: int = 600

    # Stockage PUBLIC (photo de profil artisan) -- volontairement distinct du
    # stockage privé ci-dessus (verification.doc_url) : une photo de profil
    # est censée être visible publiquement (recherche, profil détaillé),
    # contrairement à une CNI. Vide : même valeur que STORAGE_BACKEND. En
    # "s3", les médias vont dans le bucket PUBLIC, jamais le privé.
    avatar_storage_backend: Literal["local", "s3"] | None = None
    # Répertoire local, monté en lecture publique par app/main.py sous
    # /static/avatars (StaticFiles) -- jamais le même répertoire que
    # STORAGE_LOCAL_DIR (documents privés), pour ne jamais risquer de servir
    # publiquement un document de vérification par erreur de configuration.
    avatar_storage_local_dir: str = "var/public/avatars"
    # Taille maximale d'un FICHIER envoyé pour la photo de profil / de
    # couverture, en octets. Défaut 10 Mo : une photo prise au téléphone
    # dépasse couramment 4 Mo. Ce plafond ne concerne que l'envoi -- ce qui
    # est servi publiquement est toujours réencodé et redimensionné
    # (app/services/image_processing.py), donc pèse quelques centaines de Ko
    # quelle que soit la taille d'origine. Deux réglages indépendants pour
    # pouvoir les faire évoluer séparément. Exposés au front par
    # GET /artisans/me/media-constraints : une seule source de vérité.
    avatar_max_upload_bytes: int = 10 * 1024 * 1024
    cover_max_upload_bytes: int = 10 * 1024 * 1024

    # Côté le plus long de l'image SERVIE, en pixels (jamais d'agrandissement).
    # Avatar : affiché au plus en 144 px (fiche publique), 512 couvre les
    # écrans haute densité. Couverture : bandeau pleine largeur, 1600 px.
    avatar_max_side_px: int = 512
    cover_max_side_px: int = 1600

    # Plafond de pixels de l'image ENVOYÉE (largeur × hauteur lues dans
    # l'en-tête, avant tout décodage) : protège de la bombe de décompression
    # (un PNG de quelques Ko annonçant des milliards de pixels). 50 Mpx couvre
    # les capteurs de téléphone actuels (jusqu'à 50 Mpx en sortie standard).
    profile_media_max_pixels: int = 50_000_000

    # Rate limiting sur POST /api/v1/artisans/me/avatar et .../me/cover,
    # même mécanisme (fenêtre glissante, stockage RATE_LIMIT_BACKEND) que
    # RATE_LIMIT_DOCUMENT_UPLOAD_*. Budget partagé entre les deux endpoints
    # (même limiteur, même clé `user:{id}`) : ce sont deux variantes du même
    # geste ("changer une photo de mon profil public"), pas deux
    # fonctionnalités distinctes à budgétiser séparément.
    rate_limit_profile_media_upload_per_user_max: int = 20
    rate_limit_profile_media_upload_per_user_window_seconds: int = 600

    # --- Messagerie in-app (BUILD_PLAN.md §3.2, Messagerie) -------------------

    # Longueur maximale d'un message texte, en caractères (après nettoyage
    # des espaces). Large pour décrire un problème ou un devis, sans
    # autoriser des pavés qui dégraderaient le fil et le stockage.
    messaging_body_max_length: int = 2000
    # Historique : nombre de messages renvoyés par appel (défaut / plafond).
    # Le plafond borne le coût d'une requête quel que soit le client.
    messaging_history_page_size_default: int = 30
    messaging_history_page_size_max: int = 100

    # Rate limiting de l'envoi de messages texte, par utilisateur (fenêtre
    # glissante, stockage RATE_LIMIT_BACKEND). 30 / minute couvre largement
    # une conversation humaine rapide, mais bloque un script d'envoi massif.
    rate_limit_message_send_per_user_max: int = 30
    rate_limit_message_send_per_user_window_seconds: int = 60

    # Images jointes : stockage PRIVÉ, jamais monté en StaticFiles (comme les
    # documents de vérification) -- une photo d'intérieur ne doit être visible
    # que des deux participants. Vide : même valeur que STORAGE_BACKEND ; en
    # "s3", bucket PRIVÉ (comme les documents d'identité).
    message_attachment_storage_backend: Literal["local", "s3"] | None = None
    message_attachment_storage_local_dir: str = "var/message-attachments"
    # Taille maximale du fichier ENVOYÉ (une photo de téléphone dépasse
    # souvent 4 Mo). Ce qui est stocké est réencodé (EXIF/GPS retirés) et
    # redimensionné, donc bien plus léger.
    message_attachment_max_upload_bytes: int = 10 * 1024 * 1024
    # Côté le plus long de l'image stockée, en pixels (jamais d'agrandissement) :
    # assez pour lire un détail de fuite ou de tableau électrique.
    message_attachment_max_side_px: int = 1600
    # Plafond de pixels lu dans l'en-tête avant décodage (anti-bombe de
    # décompression), même valeur que pour les médias de profil.
    message_attachment_max_pixels: int = 50_000_000
    # Rate limiting de l'envoi d'images, par utilisateur : chaque envoi
    # décode, réencode et écrit un fichier -- bien plus coûteux qu'un texte.
    rate_limit_message_attachment_per_user_max: int = 20
    rate_limit_message_attachment_per_user_window_seconds: int = 600

    # WebSocket (livraison temps réel). Authentification par TICKET : jeton
    # signé dédié (type "ws"), à usage unique, de courte durée, obtenu par
    # un appel REST authentifié puis transmis dans le sous-protocole
    # WebSocket -- jamais dans l'URL (journaux), jamais l'access token lui-même.
    ws_ticket_ttl_seconds: int = 60
    # Battement de cœur applicatif : le serveur envoie un « ping » à cet
    # intervalle ; sans « pong » du client avant le délai d'expiration, la
    # connexion est considérée morte et fermée. Côté navigateur, ces pings
    # permettent aussi de détecter une connexion silencieusement coupée.
    ws_heartbeat_interval_seconds: float = 25.0
    ws_heartbeat_timeout_seconds: float = 60.0
    # Connexions WebSocket simultanées par utilisateur (plusieurs onglets ou
    # appareils) : au-delà, la plus ancienne est fermée -- borne la mémoire
    # occupée par un seul compte.
    ws_max_connections_per_user: int = 5

    # --- Demandes ----------------------------------------------------------

    # Durée de vie d'une demande OUVERTE (aucun artisan ne l'a reçue) : au-delà,
    # elle est expirée -- un besoin de dépannage vieux d'un mois n'est plus
    # d'actualité, et l'artisan ne doit pas chiffrer un problème périmé. La
    # règle s'applique d'office à la lecture et à l'envoi ;
    # scripts/expire_requests.py l'enregistre en base (statistiques).
    request_open_ttl_days: int = Field(default=30, ge=1)

    # --- Paiements (BUILD_PLAN.md §3.5) ------------------------------------

    # Règle d'arrondi de la commission (app/services/commission_calculation.py).
    # "floor" (défaut) : vers le bas, en faveur de l'artisan -- la commission
    # ne dépasse jamais le taux annoncé, écart maximal 1 FCFA au détriment de
    # Téranga. Le montant calculé est stocké sur la platform_fee à sa
    # création : changer cette règle ne modifie jamais une commission passée.
    commission_rounding: Literal["floor", "half_up", "ceil"] = "floor"

    # Plafond de SAISIE d'un nouveau taux depuis le back-office (points de
    # base : 3000 = 30 %). Garde-fou contre la faute de frappe (10000 au lieu
    # de 1000) ; la base, elle, borne déjà à 0-10000. Ne touche aucun taux
    # existant (app/services/admin_commission.py).
    commission_rate_max_bps: int = Field(default=3000, ge=0, le=10_000)

    # Fournisseur de paiement actif -- LE point de bascule sandbox -> réel
    # (app/services/payment_providers/__init__.py). "sandbox" reproduit le
    # contrat d'un agrégateur (checkout hébergé, webhook signé HMAC, event id)
    # sans argent réel ; il est refusé en prod (validate_payment_provider).
    # Brancher un agrégateur (PayDunya, CinetPay...) = un adaptateur de plus
    # + sa valeur ici + ses identifiants, sans toucher au code métier.
    # "disabled" : paiement en ligne coupé (seules les espèces sont
    # enregistrables) -- la valeur d'un déploiement sans agrégateur réel.
    payment_provider: Literal["sandbox", "disabled"] = "sandbox"
    # Secret partagé de signature des webhooks (HMAC-SHA256), fourni par
    # l'agrégateur. Obligatoire (>= 32 caractères) hors dev ; en dev avec le
    # sandbox, dérivé de JWT_SECRET s'il est vide (jamais une valeur en dur).
    payment_webhook_secret: str = ""
    # Écart maximal accepté entre l'horodatage signé d'un webhook et
    # l'horloge du serveur : au-delà, la notification est refusée (rejeu
    # d'une vieille notification interceptée). 5 min, usage des agrégateurs.
    payment_webhook_tolerance_seconds: int = 300
    # Taille maximale du corps d'un webhook : une notification de paiement
    # tient en quelques Ko ; au-delà, refus avant lecture complète (un
    # endpoint public ne doit jamais bufferiser un corps arbitraire).
    payment_webhook_max_body_bytes: int = 64 * 1024
    # Durée de validité d'une page de paiement : au-delà, un nouveau
    # checkout est ouvert (l'ancien ne peut plus être payé).
    payment_checkout_ttl_seconds: int = 1800
    # Devise unique : franc CFA BCEAO (XOF), montants entiers.
    payment_currency: Literal["XOF"] = "XOF"
    # Moyens de paiement EN LIGNE proposés (via le fournisseur, séquestre).
    payment_online_channels: Annotated[list[PaymentChannel], NoDecode] = [
        PaymentChannel.WAVE,
        PaymentChannel.ORANGE_MONEY,
        PaymentChannel.CARTE,
    ]
    # Espèces : enregistrées (pas de séquestre, commission due par l'artisan).
    payment_cash_enabled: bool = True
    # Délai maximal d'un appel au fournisseur (checkout, remboursement,
    # versement) : au-delà, l'opération échoue proprement (502), jamais
    # une requête pendue.
    payment_provider_timeout_seconds: float = 10.0
    # Moyen de versement par défaut d'un artisan qui n'en a pas choisi, et
    # moyens qu'il peut choisir (toujours vers son numéro vérifié).
    payout_default_channel: PayoutChannel = PayoutChannel.WAVE
    payout_allowed_channels: Annotated[list[PayoutChannel], NoDecode] = [
        PayoutChannel.WAVE,
        PayoutChannel.ORANGE_MONEY,
    ]
    # Rate limiting de POST /payments/init, par utilisateur : chaque appel
    # peut ouvrir un checkout chez le fournisseur.
    rate_limit_payment_init_per_user_max: int = 10
    rate_limit_payment_init_per_user_window_seconds: int = 600
    # Origine publique du front : pages de retour après un checkout. Jamais
    # une URL fournie par le client (redirection ouverte).
    frontend_public_base_url: str = "http://localhost:3000"
    # Sandbox uniquement : où le « fournisseur » simulé livre ses webhooks.
    # Vide = {BACKEND_PUBLIC_BASE_URL}/api/v1/webhooks/payments.
    sandbox_webhook_url: str = ""

    @field_validator("payment_online_channels", "payout_allowed_channels", mode="before")
    @classmethod
    def split_channels(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @model_validator(mode="after")
    def validate_payment_settings(self) -> "Settings":
        if PaymentChannel.CASH in self.payment_online_channels:
            raise ValueError("PAYMENT_ONLINE_CHANNELS ne peut pas contenir « cash ».")
        if self.payout_default_channel not in self.payout_allowed_channels:
            raise ValueError("PAYOUT_DEFAULT_CHANNEL doit figurer dans PAYOUT_ALLOWED_CHANNELS.")
        # Sandbox en production : refusé par `validate_production`, avec les
        # autres problèmes de la configuration (une seule liste).
        needs_secret = self.payment_provider not in ("disabled", "sandbox") or (
            self.payment_provider == "sandbox" and not self.is_local and not self.is_production
        )
        if needs_secret and len(self.payment_webhook_secret) < 32:
            raise ValueError(
                "PAYMENT_WEBHOOK_SECRET est requis (32 caractères minimum) hors dev : "
                "sans lui, n'importe qui pourrait forger une notification de paiement."
            )
        return self

    # Origine publique du backend, utilisée pour construire l'URL absolue
    # d'un avatar (`{backend_public_base_url}/static/avatars/...`). Une URL
    # relative ne suffit pas : front (Vercel) et back (Railway) sont deux
    # services séparés en prod (BUILD_PLAN.md §1), sur des origines
    # différentes -- le front ne peut pas deviner l'origine du back.
    backend_public_base_url: str = "http://localhost:8000"

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        """Fail-fast de PRODUCTION : refuse de démarrer sur une configuration
        de dev ou incomplète. Tous les problèmes sont listés d'un coup (pas un
        aller-retour par variable manquante). Hors production, rien ne change :
        le dev démarre sans Redis, sans S3, avec le sandbox."""
        if not self.is_production:
            return self
        problems: list[str] = []

        if looks_like_placeholder(self.jwt_secret):
            problems.append("JWT_SECRET est une valeur d'exemple : générez un secret aléatoire.")

        database = make_url(self.database_url)
        if (database.host or "").lower() in _LOCAL_HOSTS:
            problems.append("DATABASE_URL pointe vers une base locale, pas celle de production.")
        password = database.password or ""
        if not password or password in ("password", "postgres") or looks_like_placeholder(password):
            problems.append("DATABASE_URL n'a pas de mot de passe réel.")

        if self.payment_provider == "sandbox":
            problems.append(
                "PAYMENT_PROVIDER=sandbox est interdit en production : aucun argent réel ne "
                "circulerait. Agrégateur réel, ou PAYMENT_PROVIDER=disabled (espèces seulement)."
            )
        if self.payment_webhook_secret and looks_like_placeholder(self.payment_webhook_secret):
            problems.append("PAYMENT_WEBHOOK_SECRET est une valeur d'exemple.")

        if self.otp_test_whitelist or self.otp_test_code is not None:
            problems.append(
                "OTP_TEST_WHITELIST / OTP_TEST_CODE sont interdits en production : le mode OTP "
                "de test (connexion sans SMS) n'existe qu'en staging."
            )
        if self.sms_provider == "console":
            problems.append("SMS_PROVIDER=console est interdit en production : aucun SMS ne part.")
        elif self.sms_provider == "unconfigured":
            problems.append(
                "SMS_PROVIDER=unconfigured : aucun fournisseur SMS réel n'est branché, personne "
                "ne recevrait son code de connexion (voir DEPLOYMENT.md, prérequis)."
            )

        for name, backend in (
            ("STORAGE_BACKEND", self.storage_backend),
            ("AVATAR_STORAGE_BACKEND", self.avatar_storage_backend),
            ("MESSAGE_ATTACHMENT_STORAGE_BACKEND", self.message_attachment_storage_backend),
        ):
            if backend == "local":
                problems.append(
                    f"{name}=local est interdit en production : le disque du service est "
                    "éphémère, les fichiers seraient perdus au redéploiement (STORAGE_BACKEND=s3)."
                )
        if self.s3_public_base_url and not _is_public_https_url(self.s3_public_base_url):
            problems.append("S3_PUBLIC_BASE_URL doit être une URL publique HTTPS.")
        if self.s3_secret_access_key and looks_like_placeholder(self.s3_secret_access_key):
            problems.append("S3_SECRET_ACCESS_KEY est une valeur d'exemple.")

        if self.trusted_proxy_hops is None:
            problems.append(
                "TRUSTED_PROXY_HOPS doit être renseigné (1 derrière le proxy Railway) : sans "
                "lui, le rate limiting par IP verrait tous les clients comme un seul."
            )

        if self.ai_triage_provider == "mistral" and not (self.mistral_api_key or "").strip():
            problems.append("AI_TRIAGE_PROVIDER=mistral exige MISTRAL_API_KEY.")

        for name, value in (
            ("FRONTEND_PUBLIC_BASE_URL", self.frontend_public_base_url),
            ("BACKEND_PUBLIC_BASE_URL", self.backend_public_base_url),
        ):
            if not _is_public_https_url(value):
                problems.append(f"{name} doit être l'URL publique HTTPS du service ({value!r}).")

        for origin in self.cors_origins:
            if not _is_public_https_url(origin):
                problems.append(f"CORS_ORIGINS : {origin!r} doit être une origine HTTPS publique.")
        # Front et back sur deux origines (Vercel/Railway) : sans l'origine
        # du front dans CORS_ORIGINS, le navigateur bloquerait chaque appel.
        front = _origin_of(self.frontend_public_base_url)
        if front != _origin_of(self.backend_public_base_url) and front not in self.cors_origins:
            problems.append(
                f"CORS_ORIGINS doit contenir l'origine du front ({front!r}) : front et backend "
                "sont servis sur deux origines différentes."
            )

        if problems:
            raise ValueError("Configuration de production refusée :\n- " + "\n- ".join(problems))
        return self


def _origin_of(url: str) -> str:
    """Origine (`schéma://hôte[:port]`) d'une URL, en minuscules ; chaîne
    vide si ce n'est pas une URL absolue."""
    scheme, sep, rest = url.strip().partition("://")
    if not sep or not scheme or not rest:
        return ""
    host = rest.split("/", 1)[0]
    return f"{scheme.lower()}://{host.lower()}" if host else ""


def _is_public_https_url(value: str) -> bool:
    """URL `https://` vers un hôte public (jamais localhost)."""
    scheme, _, rest = value.partition("://")
    host = rest.split("/", 1)[0].rsplit(":", 1)[0].strip("[]").lower()
    return scheme == "https" and bool(host) and host not in _LOCAL_HOSTS


@lru_cache
def get_settings() -> Settings:
    return Settings()
