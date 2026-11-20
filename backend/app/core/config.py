import re
import unicodedata
from functools import lru_cache
from typing import Annotated, Literal, get_args
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.core.vapid import load_private_key as load_vapid_private_key
from app.core.vapid import load_public_key as load_vapid_public_key
from app.core.vapid import public_key_matches as vapid_public_key_matches
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


# Caractères invisibles qui ne sont PAS des « blancs » pour `str.strip()` mais
# arrivent avec un copier-coller depuis un tableau de bord ou une page web :
# indicateur d'ordre des octets (BOM), espaces et liants de largeur nulle.
_INVISIBLE_EDGE_CHARS = "\ufeff\u200b\u200c\u200d\u2060"
# Nom d'hôte DNS : même règle que botocore (botocore.utils.is_valid_endpoint_url),
# qui refuse sinon le client S3 au premier envoi (« Invalid endpoint »).
_HOSTNAME_LABELS_RE = re.compile(
    r"^((?!-)[A-Z\d-]{1,63}(?<!-)\.)*((?!-)[A-Z\d-]{1,63}(?<!-))$", re.IGNORECASE
)
# Région S3 : « auto » (R2), « eu-central-1 » (AWS, Supabase), « local »...
_S3_REGION_RE = re.compile(r"[a-z0-9-]+")
# Identifiant d'expéditeur Termii : 3 à 11 caractères alphanumériques
# (documentation Termii, Messaging API, champ `from`).
_TERMII_SENDER_RE = re.compile(r"[A-Za-z0-9]{3,11}")
# Adresse e-mail (forme simple « local@domaine.tld ») : contrôle de saisie,
# pas une validation RFC complète -- le serveur SMTP reste juge.
_EMAIL_RE = re.compile(r"[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+")


def clean_setting_value(value: str) -> str:
    """Retire les blancs (espaces, tabulations, retours à la ligne, espaces
    insécables) et les caractères invisibles en bordure d'une valeur collée."""
    previous = None
    while previous != value:
        previous = value
        value = value.strip().strip(_INVISIBLE_EDGE_CHARS)
    return value


def has_hidden_characters(value: str) -> bool:
    """Vrai si la valeur contient un blanc ou un caractère de contrôle ou de
    format (invisible), où que ce soit."""
    return any(
        char.isspace() or unicodedata.category(char) in ("Cc", "Cf", "Zs", "Zl", "Zp")
        for char in value
    )


def is_valid_https_base_url(url: str, *, allow_http: bool = False) -> bool:
    """URL de base d'une API externe : https (http seulement si `allow_http`,
    pour un faux serveur local), nom d'hôte DNS valide, aucun caractère
    invisible, ni identifiants, ni paramètres, ni fragment."""
    if has_hidden_characters(url):
        return False
    try:
        parts = urlsplit(url)
        _ = parts.port  # lève ValueError si le port n'est pas un entier
    except ValueError:
        return False
    hostname = (parts.hostname or "").removesuffix(".")
    schemes = ("https", "http") if allow_http else ("https",)
    return (
        parts.scheme in schemes
        and not (parts.username or parts.password or parts.query or parts.fragment)
        and 0 < len(hostname) <= 255
        and _HOSTNAME_LABELS_RE.match(hostname) is not None
    )


def is_valid_s3_endpoint(url: str) -> bool:
    """URL d'endpoint S3 que botocore acceptera : http(s), nom d'hôte DNS
    valide, port numérique, aucun caractère invisible."""
    if has_hidden_characters(url):
        return False
    try:
        parts = urlsplit(url)
        _ = parts.port  # lève ValueError si le port n'est pas un entier
    except ValueError:
        return False
    hostname = (parts.hostname or "").removesuffix(".")
    return (
        parts.scheme in ("http", "https")
        and 0 < len(hostname) <= 255
        and _HOSTNAME_LABELS_RE.match(hostname) is not None
    )


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

    # Canal de LIVRAISON des codes OTP (la génération, le hachage et la
    # vérification restent les nôtres, app/services/otp.py) :
    # - "console" (dev) : code écrit dans les journaux, en development/test
    #   seulement ;
    # - "termii" : envoi réel par l'API Termii (app/services/sms_termii.py),
    #   réglages TERMII_* ci-dessous ;
    # - "unconfigured" : échoue explicitement à l'envoi.
    # En PRODUCTION, "console" et "unconfigured" sont refusés au démarrage
    # (`validate_production`) : une prod où personne ne peut recevoir son
    # code de connexion ne doit jamais démarrer.
    sms_provider: Literal["console", "unconfigured", "termii"] = "console"

    # --- Termii (SMS_PROVIDER=termii, DEPLOYMENT.md) -------------------------
    # Clé d'API (tableau de bord Termii, Settings > API token). SECRET : jamais
    # journalisée, envoyée dans le CORPS des requêtes (exigence Termii), donc
    # jamais dans une URL.
    termii_api_key: str | None = None
    # Identifiant d'expéditeur enregistré chez Termii (3 à 11 caractères
    # alphanumériques). Sur WhatsApp, Termii attend le nom de l'appareil :
    # TERMII_WHATSAPP_SENDER s'il est renseigné, sinon cet identifiant.
    termii_sender_id: str | None = None
    termii_whatsapp_sender: str | None = None
    # Base de l'API PROPRE AU COMPTE, affichée dans le tableau de bord Termii
    # (Settings > API token) : Termii route chaque compte vers sa région
    # réglementaire, la documentation ne publie plus d'hôte unique. Aucune
    # valeur par défaut : un hôte deviné pourrait viser la mauvaise région.
    termii_base_url: str | None = None
    # Délai d'UN appel HTTP à Termii, nombre d'essais par canal (1 nouvel
    # essai sur panne transitoire : réseau, délai, HTTP 429/5xx), et budget
    # TOTAL de l'envoi, tous canaux et essais confondus. Le budget total doit
    # rester sous le délai du front pour un appel court (10 s,
    # frontend/src/lib/api/http.ts) : au-delà, le front abandonnerait avant
    # la réponse.
    termii_timeout_seconds: float = 4.0
    termii_max_attempts: int = Field(default=2, ge=1, le=3)
    termii_total_timeout_seconds: float = 8.0
    # Valeur du champ `channel` de Termii pour un code par WhatsApp. La
    # documentation Termii (« Send WhatsApp Token ») utilise "whatsapp_otp"
    # (code numérique de 4 à 6 chiffres, activation par le support Termii) ;
    # "whatsapp" est le canal conversationnel. Réglable sans toucher au code.
    termii_whatsapp_channel: Literal["whatsapp_otp", "whatsapp"] = "whatsapp_otp"

    # Route SMS de Termii pour les codes : "dnd" (transactionnelle, passe
    # même sur les numéros inscrits en liste anti-publicité) ou "generic".
    otp_sms_channel: Literal["dnd", "generic"] = "dnd"
    # Canal de livraison des codes : "sms" (défaut), "whatsapp", ou
    # "whatsapp_then_sms" (WhatsApp d'abord, repli SMS si WhatsApp échoue).
    otp_channel: Literal["sms", "whatsapp", "whatsapp_then_sms"] = "sms"

    # --- E-mails aux administrateurs (DEPLOYMENT.md, « E-mails ») ----------
    # Fournisseur :
    # - "console" (défaut dev/test : rien n'est envoyé, l'e-mail est
    #   seulement journalisé) ;
    # - "brevo" (envoi réel par l'API HTTP de Brevo, port 443 : la voie à
    #   utiliser sur Render, qui bloque le SMTP sortant) ;
    # - "smtp" (envoi réel, réglages SMTP_* : inutilisable sur Render).
    email_provider: Literal["console", "smtp", "brevo"] = "console"
    # Brevo : clé d'API (Brevo > SMTP & API > Clés API). SECRET : envoyée
    # dans un en-tête, jamais journalisée ni affichée dans une erreur.
    brevo_api_key: str | None = None
    # Base de l'API Brevo (documentation officielle) ; réglable sans code.
    brevo_api_base_url: str = "https://api.brevo.com/v3"
    # Délai maximal d'un appel à Brevo : l'envoi est en arrière-plan, jamais
    # sur le chemin de la réponse à l'artisan.
    brevo_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Serveur SMTP. Port 587 + STARTTLS (défaut), ou 465 + SSL implicite.
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    # Identifiant et mot de passe SMTP. Mot de passe = SECRET : jamais
    # journalisé ni affiché dans une erreur de configuration.
    smtp_user: str | None = None
    smtp_password: str | None = None
    # Délai maximal d'un envoi (connexion + échange) : un serveur lent ne
    # bloque jamais la requête de l'artisan (l'envoi est fait en arrière-plan).
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Expéditeur des e-mails (souvent le compte SMTP lui-même, ex. Gmail).
    email_from: str | None = None
    # Destinataires des notifications d'administration (nouvelle demande de
    # vérification...), séparés par des virgules. Vide = aucune notification.
    admin_notification_emails: Annotated[list[str], NoDecode] = []

    @field_validator(
        "smtp_host",
        "smtp_user",
        "smtp_password",
        "email_from",
        "brevo_api_key",
        mode="before",
    )
    @classmethod
    def clean_email_value(cls, v: object) -> object:
        # Valeurs collées dans un tableau de bord : même nettoyage que S3_*.
        if isinstance(v, str):
            v = clean_setting_value(v)
            return v or None
        return v

    @field_validator("brevo_api_base_url", mode="before")
    @classmethod
    def clean_brevo_api_base_url(cls, v: object) -> object:
        # Nettoyée sans devenir None (valeur par défaut documentée) : une
        # valeur vide est signalée comme invalide avec EMAIL_PROVIDER=brevo.
        return clean_setting_value(v) if isinstance(v, str) else v

    @field_validator("admin_notification_emails", mode="before")
    @classmethod
    def split_admin_notification_emails(cls, v: object) -> object:
        if isinstance(v, str):
            return [address for part in v.split(",") if (address := clean_setting_value(part))]
        return v

    @model_validator(mode="after")
    def validate_email_settings(self) -> "Settings":
        """Adresses vérifiées quel que soit le fournisseur ; avec "smtp" ou
        "brevo", réglages complets exigés. Tous les problèmes listés d'un coup,
        jamais un mot de passe ni une clé d'API."""
        problems: list[str] = []
        for address in self.admin_notification_emails:
            if not _EMAIL_RE.fullmatch(address):
                problems.append(
                    f"ADMIN_NOTIFICATION_EMAILS : {address!r} n'est pas une adresse e-mail."
                )
        if self.email_from and not _EMAIL_RE.fullmatch(self.email_from):
            problems.append(f"EMAIL_FROM : {self.email_from!r} n'est pas une adresse e-mail.")
        if self.email_provider == "smtp":
            missing = [
                name
                for name, value in (
                    ("SMTP_HOST", self.smtp_host),
                    ("SMTP_USER", self.smtp_user),
                    ("SMTP_PASSWORD", self.smtp_password),
                    ("EMAIL_FROM", self.email_from),
                )
                if not value
            ]
            if missing:
                problems.append(f"E-mail SMTP incomplet, à renseigner : {', '.join(missing)}.")
            if not self.admin_notification_emails:
                problems.append(
                    "ADMIN_NOTIFICATION_EMAILS est vide : avec EMAIL_PROVIDER=smtp, au moins un "
                    "destinataire est attendu."
                )
            if self.smtp_host and has_hidden_characters(self.smtp_host):
                problems.append(f"SMTP_HOST invalide ({self.smtp_host!r}).")
        if self.email_provider == "brevo":
            missing = [
                name
                for name, value in (
                    ("BREVO_API_KEY", self.brevo_api_key),
                    ("EMAIL_FROM", self.email_from),
                )
                if not value
            ]
            if missing:
                problems.append(f"E-mail Brevo incomplet, à renseigner : {', '.join(missing)}.")
            if not self.admin_notification_emails:
                problems.append(
                    "ADMIN_NOTIFICATION_EMAILS est vide : avec EMAIL_PROVIDER=brevo, au moins un "
                    "destinataire est attendu."
                )
            if self.brevo_api_key and has_hidden_characters(self.brevo_api_key):
                problems.append(
                    "BREVO_API_KEY contient un espace ou un caractère invisible (valeur non "
                    "affichée) : la ressaisir."
                )
            if not is_valid_https_base_url(self.brevo_api_base_url):
                problems.append(
                    f"BREVO_API_BASE_URL invalide ({self.brevo_api_base_url!r}) : URL https:// "
                    "attendue."
                )
        if problems:
            raise ValueError("E-mail mal configuré :\n- " + "\n- ".join(problems))
        return self

    @field_validator(
        "termii_api_key",
        "termii_sender_id",
        "termii_whatsapp_sender",
        "termii_base_url",
        mode="before",
    )
    @classmethod
    def clean_termii_value(cls, v: object) -> object:
        # Valeurs collées dans un tableau de bord : même nettoyage que S3_*
        # (retour à la ligne, espaces, caractères invisibles en bordure).
        if isinstance(v, str):
            v = clean_setting_value(v)
            return v or None
        return v

    @model_validator(mode="after")
    def validate_termii(self) -> "Settings":
        """Fournisseur Termii : tous les problèmes listés d'un coup, jamais la
        clé d'API. Sans effet si SMS_PROVIDER n'est pas `termii`."""
        if self.sms_provider != "termii":
            return self
        problems: list[str] = []
        missing = [
            name
            for name, value in (
                ("TERMII_API_KEY", self.termii_api_key),
                ("TERMII_SENDER_ID", self.termii_sender_id),
                ("TERMII_BASE_URL", self.termii_base_url),
            )
            if not value
        ]
        if missing:
            problems.append(f"Termii incomplet, à renseigner : {', '.join(missing)}.")
        if self.termii_api_key and has_hidden_characters(self.termii_api_key):
            problems.append(
                "TERMII_API_KEY contient un espace ou un caractère invisible (valeur non "
                "affichée) : la ressaisir."
            )
        for name, sender in (
            ("TERMII_SENDER_ID", self.termii_sender_id),
            ("TERMII_WHATSAPP_SENDER", self.termii_whatsapp_sender),
        ):
            if sender and not _TERMII_SENDER_RE.fullmatch(sender):
                problems.append(
                    f"{name} invalide ({sender!r}) : 3 à 11 caractères alphanumériques "
                    "(exigence Termii)."
                )
        if self.termii_base_url and not is_valid_https_base_url(
            self.termii_base_url, allow_http=self.is_local
        ):
            problems.append(
                f"TERMII_BASE_URL invalide ({self.termii_base_url!r}) : l'URL https:// "
                "affichée dans le tableau de bord Termii, sans espace ni caractère invisible."
            )
        if not 0 < self.termii_timeout_seconds <= self.termii_total_timeout_seconds:
            problems.append(
                "TERMII_TIMEOUT_SECONDS doit être positif et ne pas dépasser "
                "TERMII_TOTAL_TIMEOUT_SECONDS."
            )
        if self.otp_channel != "sms" and not 4 <= self.otp_code_length <= 6:
            problems.append(
                f"OTP_CHANNEL={self.otp_channel} : le code WhatsApp de Termii compte 4 à 6 "
                f"chiffres, OTP_CODE_LENGTH vaut {self.otp_code_length}."
            )
        if problems:
            raise ValueError("Fournisseur SMS Termii mal configuré :\n- " + "\n- ".join(problems))
        return self

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
        # Pooler TRANSACTION de Supabase (port 6543) : il n'accepte pas les
        # instructions préparées qu'asyncpg emploie pour chaque requête
        # (erreurs aléatoires « prepared statement ... does not exist ») et ne
        # garde pas la même connexion serveur d'une transaction à l'autre (le
        # verrou des migrations de scripts/serve.py n'y tiendrait pas).
        # Refus net plutôt que des pannes intermittentes en beta.
        host = (url.host or "").lower()
        if host.endswith(".pooler.supabase.com") and url.port == 6543:
            raise ValueError(
                "DATABASE_URL vise le pooler TRANSACTION de Supabase (port 6543), incompatible "
                "avec asyncpg : utiliser le session pooler, port 5432 (DEPLOYMENT.md §12.4)."
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
        # Non-énumération : avec le fournisseur `unconfigured`, un numéro HORS
        # liste ferait échouer request-otp (erreur 500) quand un numéro listé
        # obtient 204 -- la différence révélerait qui figure sur la liste.
        # Sans fournisseur réel en staging : `console` (le code n'y est jamais
        # journalisé hors development/test, la réponse reste identique).
        if self.sms_provider == "unconfigured":
            raise ValueError(
                "Mode OTP de test avec SMS_PROVIDER=unconfigured : les numéros hors liste "
                "échoueraient (500) et révéleraient la liste. Utiliser SMS_PROVIDER=console "
                "en staging tant qu'aucun fournisseur réel n'est branché."
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
    # Adressage « path-style » (https://endpoint/bucket/clé) plutôt que
    # « virtual-host » (https://bucket.endpoint/clé). EXIGÉ par Supabase
    # Storage et MinIO, toléré par R2. Vide (défaut) : activé dès que
    # S3_ENDPOINT_URL est renseigné, laissé au choix de boto3 sur AWS S3 (sans
    # endpoint, comportement inchangé). `true` / `false` pour forcer.
    s3_force_path_style: bool | None = None

    @property
    def s3_addressing_style(self) -> Literal["path", "virtual"] | None:
        """Adressage S3 effectif : "path", "virtual", ou None (choix de boto3)."""
        if self.s3_force_path_style is None:
            return "path" if self.s3_endpoint_url else None
        return "path" if self.s3_force_path_style else "virtual"

    @field_validator(
        "avatar_storage_backend",
        "message_attachment_storage_backend",
        "s3_endpoint_url",
        "s3_access_key_id",
        "s3_secret_access_key",
        "s3_private_bucket",
        "s3_public_bucket",
        "s3_public_base_url",
        "s3_force_path_style",
        mode="before",
    )
    @classmethod
    def empty_storage_value_means_none(cls, v: object) -> object:
        # Valeurs COLLÉES dans un tableau de bord (Render, Railway) : un retour
        # à la ligne ou un espace en bordure, invisibles à l'écran, rendaient
        # l'endpoint inutilisable par boto3 (« Invalid endpoint ») au premier
        # envoi de fichier. Retirés ici ; vide après nettoyage = absent.
        if isinstance(v, str):
            v = clean_setting_value(v)
            return v or None
        return v

    @field_validator("s3_region", mode="before")
    @classmethod
    def clean_s3_region(cls, v: object) -> object:
        # Même nettoyage ; une région vide est signalée par `validate_storage`.
        return clean_setting_value(v) if isinstance(v, str) else v

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
        # Tous les problèmes d'un coup (pas un redéploiement par variable),
        # sans JAMAIS recopier une clé ou un secret : seules les valeurs non
        # secrètes (endpoint, région, buckets, URL publique) sont citées, en
        # repr() pour rendre visible un caractère invisible.
        problems: list[str] = []
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
            problems.append(f"Stockage S3 incomplet, à renseigner : {', '.join(missing)}.")
        for name, secret in (
            ("S3_ACCESS_KEY_ID", self.s3_access_key_id),
            ("S3_SECRET_ACCESS_KEY", self.s3_secret_access_key),
        ):
            if secret and has_hidden_characters(secret):
                problems.append(
                    f"{name} contient un espace ou un caractère invisible (valeur non affichée) : "
                    "la ressaisir."
                )
        if self.s3_endpoint_url and not is_valid_s3_endpoint(self.s3_endpoint_url):
            problems.append(
                f"S3_ENDPOINT_URL n'est pas une URL d'endpoint valide ({self.s3_endpoint_url!r}) : "
                "attendu https://hote/chemin, sans espace ni caractère invisible."
            )
        if not _S3_REGION_RE.fullmatch(self.s3_region):
            problems.append(
                f"S3_REGION invalide ({self.s3_region!r}) : attendu une région comme "
                "« auto » ou « eu-central-1 »."
            )
        for name, bucket in (
            ("S3_PRIVATE_BUCKET", self.s3_private_bucket),
            ("S3_PUBLIC_BUCKET", self.s3_public_bucket),
        ):
            if bucket and (has_hidden_characters(bucket) or "/" in bucket):
                problems.append(
                    f"{name} invalide ({bucket!r}) : un nom de bucket, sans espace, « / » ni "
                    "caractère invisible."
                )
        if self.s3_private_bucket and self.s3_private_bucket == self.s3_public_bucket:
            problems.append(
                "S3_PRIVATE_BUCKET et S3_PUBLIC_BUCKET doivent être deux buckets différents : "
                "un document d'identité ne doit jamais pouvoir se retrouver dans un bucket public."
            )
        base_url = self.s3_public_base_url or ""
        if (
            public_on_s3
            and base_url
            and (
                not base_url.startswith(("https://", "http://")) or has_hidden_characters(base_url)
            )
        ):
            problems.append(
                f"S3_PUBLIC_BASE_URL doit être une URL http(s) absolue, sans espace ni caractère "
                f"invisible ({base_url!r})."
            )
        if problems:
            raise ValueError("Stockage S3 mal configuré :\n- " + "\n- ".join(problems))
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

    # --- Notifications push (Web Push, application installable) ----------

    # Interrupteur EXPLICITE : sans lui, aucun abonnement n'est accepté et
    # aucun envoi n'est tenté. Activé, les trois réglages VAPID_* sont exigés
    # dès le démarrage (fail-fast, `validate_web_push`).
    web_push_enabled: bool = False
    # Paire de clés VAPID (RFC 8292), base64url, produite par
    # `uv run python scripts/generate_vapid_keys.py` (voir app/core/vapid.py).
    # La clé publique est remise au navigateur ; la clé privée est un SECRET
    # (jamais journalisée, jamais affichée dans une erreur). Changer de paire
    # invalide TOUS les abonnements existants (chaque appareil devra se
    # réabonner) : à ne faire qu'en cas de fuite.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    # Contact de l'émetteur, transmis aux services de push (Google, Mozilla,
    # Apple, Microsoft) : « mailto:adresse » ou URL https://. Apple l'exige.
    vapid_subject: str | None = None
    # Durée pendant laquelle le service de push garde une notification pour
    # un appareil éteint ou hors réseau (0 = livrer tout de suite ou jamais ;
    # plafond du protocole : 28 jours).
    web_push_ttl_seconds: int = Field(default=86_400, ge=0, le=2_419_200)
    # Délai maximal d'un envoi : en arrière-plan, jamais sur le chemin de la
    # réponse à l'expéditeur du message.
    web_push_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    # Appareils abonnés par compte : au-delà, le plus ancien est oublié (borne
    # les envois et la table pour un même utilisateur).
    web_push_max_subscriptions_per_user: int = Field(default=10, ge=1, le=50)
    # Hôtes autorisés pour l'adresse d'abonnement (`endpoint`) fournie par le
    # navigateur, comparés au nom exact ou en suffixe (« .hôte ») : le serveur
    # n'envoie JAMAIS de requête vers une adresse arbitraire (protection SSRF).
    # Défaut : services de push de Chrome/Android/Edge Chromium (FCM),
    # Firefox (Mozilla), Safari/iOS (Apple) et Edge/Windows (WNS).
    web_push_allowed_endpoint_hosts: Annotated[list[str], NoDecode] = [
        "fcm.googleapis.com",
        "push.services.mozilla.com",
        "push.apple.com",
        "notify.windows.com",
    ]
    # Budget d'(dés)abonnements par utilisateur : borne les écritures d'un
    # script, sans gêner un usage normal (quelques appareils).
    rate_limit_push_subscription_per_user_max: int = 20
    rate_limit_push_subscription_per_user_window_seconds: int = 600

    @field_validator("vapid_public_key", "vapid_private_key", "vapid_subject", mode="before")
    @classmethod
    def clean_vapid_value(cls, v: object) -> object:
        # Valeurs collées dans un tableau de bord : même nettoyage que S3_*.
        if isinstance(v, str):
            v = clean_setting_value(v)
            return v or None
        return v

    @field_validator("web_push_allowed_endpoint_hosts", mode="before")
    @classmethod
    def split_web_push_allowed_endpoint_hosts(cls, v: object) -> object:
        if isinstance(v, str):
            return [
                host.lower().removeprefix(".")
                for part in v.split(",")
                if (host := clean_setting_value(part))
            ]
        return v

    @model_validator(mode="after")
    def validate_web_push(self) -> "Settings":
        """Push activé : clés VAPID valides ET appariées, contact au bon
        format, hôtes autorisés plausibles. Tous les problèmes listés d'un
        coup, jamais la clé privée."""
        if not self.web_push_enabled:
            return self
        problems: list[str] = []
        missing = [
            name
            for name, value in (
                ("VAPID_PUBLIC_KEY", self.vapid_public_key),
                ("VAPID_PRIVATE_KEY", self.vapid_private_key),
                ("VAPID_SUBJECT", self.vapid_subject),
            )
            if not value
        ]
        if missing:
            problems.append(
                f"WEB_PUSH_ENABLED=true mais à renseigner : {', '.join(missing)} "
                "(clés : uv run python scripts/generate_vapid_keys.py)."
            )
        public_ok = private_ok = False
        if self.vapid_public_key:
            try:
                load_vapid_public_key(self.vapid_public_key)
                public_ok = True
            except ValueError:
                problems.append(
                    "VAPID_PUBLIC_KEY invalide : point P-256 non compressé en base64url "
                    "(65 octets) attendu."
                )
        if self.vapid_private_key:
            try:
                load_vapid_private_key(self.vapid_private_key)
                private_ok = True
            except ValueError:
                problems.append(
                    "VAPID_PRIVATE_KEY invalide (valeur non affichée) : clé P-256 brute en "
                    "base64url (32 octets) attendue."
                )
        if (
            public_ok
            and private_ok
            and self.vapid_public_key
            and self.vapid_private_key
            and not vapid_public_key_matches(self.vapid_public_key, self.vapid_private_key)
        ):
            problems.append(
                "VAPID_PUBLIC_KEY ne correspond pas à VAPID_PRIVATE_KEY : les deux doivent venir "
                "de la MÊME paire (sinon tous les envois seraient refusés)."
            )
        if self.vapid_subject and not _is_valid_vapid_subject(self.vapid_subject):
            problems.append(
                f"VAPID_SUBJECT invalide ({self.vapid_subject!r}) : « mailto:adresse » ou "
                "URL https:// attendue."
            )
        if not self.web_push_allowed_endpoint_hosts:
            problems.append("WEB_PUSH_ALLOWED_ENDPOINT_HOSTS est vide : aucun envoi possible.")
        for host in self.web_push_allowed_endpoint_hosts:
            if not _HOSTNAME_LABELS_RE.match(host) or "." not in host:
                problems.append(f"WEB_PUSH_ALLOWED_ENDPOINT_HOSTS : {host!r} n'est pas un hôte.")
        if problems:
            raise ValueError("Notifications push mal configurées :\n- " + "\n- ".join(problems))
        return self

    # --- Demandes ----------------------------------------------------------

    # Durée de vie d'une demande OUVERTE (aucun artisan ne l'a reçue) : au-delà,
    # elle est expirée -- un besoin de dépannage vieux d'un mois n'est plus
    # d'actualité, et l'artisan ne doit pas chiffrer un problème périmé. La
    # règle s'applique d'office à la lecture et à l'envoi ;
    # scripts/expire_requests.py l'enregistre en base (statistiques).
    request_open_ttl_days: int = Field(default=30, ge=1)

    # --- Litiges -------------------------------------------------------------

    # Fenêtre, en heures, pendant laquelle une partie peut encore signaler un
    # problème APRÈS la confirmation de fin des travaux (`terminee` ->
    # `litige`). 0 = désactivée (litige possible seulement en cours). Seulement
    # sans paiement en ligne déjà versé : le versement différé du séquestre
    # pendant la fenêtre viendra avec le branchement de l'agrégateur
    # (DEPLOYMENT.md §16).
    dispute_window_hours: int = Field(default=72, ge=0, le=720)

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
        if self.termii_api_key and looks_like_placeholder(self.termii_api_key):
            problems.append("TERMII_API_KEY est une valeur d'exemple.")
        if self.brevo_api_key and looks_like_placeholder(self.brevo_api_key):
            problems.append("BREVO_API_KEY est une valeur d'exemple.")

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


def _is_valid_vapid_subject(subject: str) -> bool:
    """Contact VAPID (RFC 8292 §2.1) : « mailto:adresse » ou URL https://."""
    if subject.startswith("mailto:"):
        return _EMAIL_RE.fullmatch(subject.removeprefix("mailto:")) is not None
    return is_valid_https_base_url(subject)


def _is_public_https_url(value: str) -> bool:
    """URL `https://` vers un hôte public (jamais localhost)."""
    scheme, _, rest = value.partition("://")
    host = rest.split("/", 1)[0].rsplit(":", 1)[0].strip("[]").lower()
    return scheme == "https" and bool(host) and host not in _LOCAL_HOSTS


@lru_cache
def get_settings() -> Settings:
    return Settings()
