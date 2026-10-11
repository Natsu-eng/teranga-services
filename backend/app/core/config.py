from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.models.enums import VerificationDocType


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

    # Stockage des compteurs de TOUS les rate limitings (OTP, triage IA,
    # documents, médias de profil) -- voir app/services/rate_limit.py.
    # - "postgres" : table `rate_limit_hit`, partagée par toutes les
    #   instances et persistante (survit à un redémarrage/déploiement).
    # - "memory" : état local au processus, pour le dev et les tests.
    # Non renseigné : "memory" en dev, "postgres" en staging/prod. "memory"
    # explicitement demandé en staging/prod est REFUSÉ au démarrage
    # (`validate_rate_limit_backend`) : derrière plusieurs instances, chacune
    # appliquerait sa propre limite (limite réelle multipliée d'autant), et
    # chaque redéploiement remettrait tous les compteurs à zéro.
    rate_limit_backend: Literal["memory", "postgres"] | None = None

    @model_validator(mode="after")
    def validate_rate_limit_backend(self) -> "Settings":
        if self.rate_limit_backend is None:
            self.rate_limit_backend = "memory" if self.app_env == "dev" else "postgres"
        elif self.rate_limit_backend == "memory" and self.app_env != "dev":
            raise ValueError(
                f"RATE_LIMIT_BACKEND=memory est interdit avec APP_ENV={self.app_env} : "
                "les limites ne seraient ni partagées entre instances ni conservées au "
                "redémarrage. Utilisez RATE_LIMIT_BACKEND=postgres (ou laissez-la vide)."
            )
        return self

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
    # Un fournisseur cloud privé reste à choisir avant la prod (même
    # principe fail-fast documenté que sms_provider/ai_triage_provider) :
    # aucune valeur autre que "local" n'est implémentée aujourd'hui.
    storage_backend: Literal["local"] = "local"
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
    # contrairement à une CNI. Même principe fail-fast que STORAGE_BACKEND :
    # "local" est le seul fournisseur implémenté aujourd'hui.
    avatar_storage_backend: Literal["local"] = "local"
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
    # que des deux participants. Même principe fail-fast que STORAGE_BACKEND.
    message_attachment_storage_backend: Literal["local"] = "local"
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

    # Origine publique du backend, utilisée pour construire l'URL absolue
    # d'un avatar (`{backend_public_base_url}/static/avatars/...`). Une URL
    # relative ne suffit pas : front (Vercel) et back (Railway) sont deux
    # services séparés en prod (BUILD_PLAN.md §1), sur des origines
    # différentes -- le front ne peut pas deviner l'origine du back.
    backend_public_base_url: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
