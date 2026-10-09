# Téranga Services — Backend

API métier de Téranga Services (FastAPI). C'est le service `backend/` du monorepo — voir le [README racine](../README.md) pour la présentation du produit et la topologie complète (frontend + backend).

Pas encore de modèle métier à ce stade (Lot 6 — socle uniquement) : ce service expose un squelette FastAPI qui démarre, se connecte à Postgres, migre son schéma via Alembic, et a sa propre porte de qualité.

## Stack technique

| Domaine | Choix |
| --- | --- |
| Langage | Python 3.12+ |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.x (mode async, driver `asyncpg`) |
| Migrations | Alembic (async) |
| Config | Pydantic v2 + pydantic-settings |
| Dépendances | [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`) |
| Qualité | ruff (lint + format), mypy (strict), pytest + pytest-asyncio + httpx |

## Prérequis

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- PostgreSQL en local (aucune valeur de connexion n'est fournie par défaut par l'application)

## Créer la base locale

```bash
createdb teranga
```

(ou l'équivalent via pgAdmin / pratique existante — le nom de la base est libre, il sera renseigné dans `DATABASE_URL`.)

## Installation

Toutes les commandes ci-dessous s'exécutent depuis ce dossier (`backend/`).

1. Copier `.env.example` vers `.env` et renseigner vos propres valeurs (au minimum `DATABASE_URL`) :

   ```bash
   cp .env.example .env
   ```

2. Installer les dépendances (crée `.venv/` automatiquement) :

   ```bash
   uv sync
   ```

## Appliquer les migrations

```bash
uv run alembic upgrade head
```

Pour revenir en arrière d'une révision :

```bash
uv run alembic downgrade -1
```

## Jeu de données de développement

Sème un jeu de données cohérent (métiers, taux de commission par défaut,
les 3 artisans du mock frontend avec de vraies coordonnées à Dakar, des
avis liés à des interventions terminées). Idempotent : relancer la commande
ne duplique rien. **Jamais exécuté automatiquement** — toujours à la main,
après les migrations :

```bash
uv run python scripts/seed.py
```

Détail du contenu semé et des choix de conception : voir l'en-tête de
[scripts/seed.py](scripts/seed.py).

## Bootstrap du premier admin

Le rôle `admin` ne s'obtient **jamais** via l'application (aucun endpoint,
aucun paramètre d'API) -- c'est une décision de sécurité actée
(BUILD_PLAN.md §4.4). Le **seul** moyen de créer un admin est ce script,
qui promeut un utilisateur **déjà inscrit** (par téléphone + OTP, comme
n'importe quel compte) :

```bash
uv run python scripts/create_admin.py +221771234567
```

Demande une confirmation interactive avant d'agir ; `--yes` pour l'ignorer
(scripts/CI). Refuse explicitement un numéro qui ne correspond à aucun
compte -- ce script ne crée jamais de compte lui-même. Idempotent :
relancer sur un numéro déjà admin est un succès silencieux, pas une erreur.

## Lancer le serveur

```bash
uv run uvicorn app.main:app --reload --port 8000
```

- API : <http://localhost:8000>
- Documentation OpenAPI interactive : <http://localhost:8000/docs>
- Liveness : `GET /api/v1/health`
- Readiness (vérifie Postgres) : `GET /api/v1/health/ready`

## Variables d'environnement

| Variable | Requise | Description |
| --- | --- | --- |
| `DATABASE_URL` | Oui | URL de connexion Postgres, driver `asyncpg` obligatoire. Aucune valeur par défaut : le démarrage échoue explicitement si absente ou malformée. |
| `APP_ENV` | Non (`dev`) | `dev` \| `staging` \| `prod`. Contrôle le format des logs (lisible en dev, JSON en prod) et si le provider SMS console journalise le code OTP. |
| `LOG_LEVEL` | Non (`INFO`) | Niveau de log Python standard. |
| `CORS_ORIGINS` | Non (vide) | Origines autorisées, séparées par des virgules. Pas de wildcard. |
| `JWT_SECRET` | Oui | Secret de signature des JWT. Aucune valeur par défaut : le démarrage échoue si absent ou trop court (< 32 caractères). |
| `JWT_ACCESS_TTL_SECONDS` | Non (`900`) | Durée de vie de l'access token (secondes). |
| `JWT_REFRESH_TTL_SECONDS` | Non (`2592000`) | Durée de vie du refresh token (secondes, 30 jours par défaut). |
| `SMS_PROVIDER` | Non (`console`) | `console` \| `unconfigured`. Fournisseur d'envoi des codes OTP -- voir [Authentification](#authentification-téléphone--otp). |
| `PHONE_DEFAULT_REGION` | Non (`SN`) | Région ISO 3166-1 alpha-2 utilisée pour interpréter un numéro écrit sans indicatif. |
| `PHONE_ALLOWED_REGIONS` | Non (`SN`) | Régions dont les numéros sont acceptés, séparées par des virgules. |
| `OTP_CODE_LENGTH` | Non (`6`) | Longueur du code OTP (chiffres). |
| `OTP_TTL_SECONDS` | Non (`300`) | TTL du code OTP (secondes, 5 min par défaut). |
| `OTP_MAX_ATTEMPTS` | Non (`5`) | Tentatives de vérification autorisées avant invalidation du code. |
| `OTP_HASH_ITERATIONS` | Non (`600000`) | Itérations PBKDF2-HMAC-SHA256 pour le hachage du code OTP. |
| `RATE_LIMIT_BACKEND` | Non (`memory` en dev, `postgres` sinon) | Stockage des compteurs de rate limiting : `postgres` (table `rate_limit_hit`, partagée entre instances, persistante) ou `memory` (processus, dev/tests). `memory` est refusé hors dev. |
| `RATE_LIMIT_OTP_PER_PHONE_MAX` | Non (`3`) | Nombre max de `request-otp` par numéro sur la fenêtre glissante. |
| `RATE_LIMIT_OTP_PER_PHONE_WINDOW_SECONDS` | Non (`600`) | Largeur de la fenêtre glissante par numéro (secondes). |
| `RATE_LIMIT_OTP_PER_IP_MAX` | Non (`10`) | Nombre max de `request-otp` par IP sur la fenêtre glissante. |
| `RATE_LIMIT_OTP_PER_IP_WINDOW_SECONDS` | Non (`600`) | Largeur de la fenêtre glissante par IP (secondes). |
| `ARTISAN_SEARCH_DEFAULT_RADIUS_M` | Non (`10000`) | Rayon de recherche par défaut (mètres) si `radius_m` n'est pas fourni sur `GET /artisans`. |
| `ARTISAN_SEARCH_MAX_RADIUS_M` | Non (`50000`) | Plafond dur du rayon de recherche (mètres). |
| `PAGINATION_PAGE_SIZE_DEFAULT` | Non (`20`) | Taille de page par défaut, réutilisée par `GET /artisans` et `GET /artisans/{id}/reviews`. |
| `PAGINATION_PAGE_SIZE_MAX` | Non (`50`) | Plafond de taille de page. |
| `PAGINATION_MAX_PAGE` | Non (`50`) | Page maximale autorisée -- au-delà, `422 PAGE_HORS_BORNES`. |
| `VERIFICATION_REQUIRED_DOC_TYPES` | Non (`cni,selfie`) | Types de documents requis pour `verified_status=VERIFIED`, séparés par des virgules. |
| `AI_TRIAGE_PROVIDER` | Non (`heuristic`) | `mistral` \| `heuristic`. Fournisseur actif pour `POST /api/v1/ai/analyze` -- voir [Triage IA](#triage-ia-lot-11). |
| `MISTRAL_API_KEY` | Non (vide) | Requise uniquement si `AI_TRIAGE_PROVIDER=mistral`. Absente, le provider échoue proprement (fallback heuristique) sans jamais tenter l'appel réseau. |
| `MISTRAL_MODEL` | Non (`mistral-small-latest`) | Modèle Mistral utilisé pour le triage. |
| `MISTRAL_API_BASE_URL` | Non (`https://api.mistral.ai/v1`) | URL de base de l'API Mistral. |
| `MISTRAL_TIMEOUT_SECONDS` | Non (`10`) | Timeout explicite sur l'appel Mistral (secondes) -- au-delà, fallback heuristique. |
| `RATE_LIMIT_AI_ANALYZE_PER_IP_MAX` | Non (`20`) | Nombre max de `POST /ai/analyze` par IP sur la fenêtre glissante. |
| `RATE_LIMIT_AI_ANALYZE_PER_IP_WINDOW_SECONDS` | Non (`600`) | Largeur de la fenêtre glissante par IP (secondes). |
| `STORAGE_BACKEND` | Non (`local`) | `local` (seul implémenté). Fournisseur de stockage des documents de vérification -- voir [Onboarding artisan](#onboarding-artisan-profil-métiers-documents). |
| `STORAGE_LOCAL_DIR` | Non (`var/artisan-documents`) | Répertoire de stockage local, relatif à `backend/` ou chemin absolu. |
| `STORAGE_MAX_UPLOAD_BYTES` | Non (`8388608`) | Taille maximale d'un document uploadé (octets, 8 Mo par défaut). |
| `RATE_LIMIT_DOCUMENT_UPLOAD_PER_USER_MAX` | Non (`10`) | Nombre max d'uploads de documents par utilisateur sur la fenêtre glissante. |
| `RATE_LIMIT_DOCUMENT_UPLOAD_PER_USER_WINDOW_SECONDS` | Non (`600`) | Largeur de la fenêtre glissante par utilisateur (secondes). |
| `AVATAR_STORAGE_BACKEND` | Non (`local`) | `local` (seul implémenté). Stockage PUBLIC des médias de profil (avatar et couverture), distinct du stockage privé des documents. |
| `AVATAR_STORAGE_LOCAL_DIR` | Non (`var/public/avatars`) | Répertoire servi en lecture publique sous `/static/avatars`, relatif à `backend/` ou chemin absolu. |
| `AVATAR_MAX_UPLOAD_BYTES` | Non (`10485760`) | Taille maximale du fichier envoyé pour une photo de profil (octets, 10 Mo). Le front la lit via `GET /artisans/me/media-constraints`. |
| `COVER_MAX_UPLOAD_BYTES` | Non (`10485760`) | Idem pour la photo de couverture. |
| `AVATAR_MAX_SIDE_PX` | Non (`512`) | Côté le plus long de l'avatar servi (pixels), après réencodage. |
| `COVER_MAX_SIDE_PX` | Non (`1600`) | Côté le plus long de la couverture servie (pixels), après réencodage. |
| `PROFILE_MEDIA_MAX_PIXELS` | Non (`50000000`) | Plafond largeur × hauteur d'une image envoyée, vérifié avant décodage (anti-bombe de décompression). |
| `RATE_LIMIT_PROFILE_MEDIA_UPLOAD_PER_USER_MAX` | Non (`20`) | Nombre max d'envois de photo (avatar + couverture, budget partagé) par utilisateur sur la fenêtre glissante. |
| `RATE_LIMIT_PROFILE_MEDIA_UPLOAD_PER_USER_WINDOW_SECONDS` | Non (`600`) | Largeur de la fenêtre glissante par utilisateur (secondes). |
| `BACKEND_PUBLIC_BASE_URL` | Non (`http://localhost:8000`) | Origine publique du backend, préfixe des URL absolues d'avatar/couverture. **À renseigner en prod.** |

Voir [.env.example](.env.example) pour le détail documenté de chaque variable.

## Authentification (téléphone + OTP)

Flux : `POST /api/v1/auth/request-otp` (toujours 204, non énumérant) →
`POST /api/v1/auth/verify-otp` (crée le compte au premier login, renvoie
`{ access, refresh, user }`) → requêtes authentifiées via
`Authorization: Bearer <access>`. `POST /api/v1/auth/refresh` fait tourner
la session (rotation, l'ancien refresh est révoqué) ; `POST /auth/logout`
et `POST /auth/logout-all` révoquent respectivement une session ou toutes.
Détail complet des garde-fous de sécurité : [BUILD_PLAN.md §4](../BUILD_PLAN.md#4-authentification-téléphone--otp).

**Provider SMS** : `SMS_PROVIDER=console` (défaut, dev) journalise le code
en clair dans les logs -- uniquement si `APP_ENV=dev` (vérifié deux fois :
au choix du provider *et* dans le provider lui-même, pour ne jamais faire
fuiter un code hors dev même mal configuré). Aucun fournisseur SMS
commercial n'est branché à ce stade ; ce choix reste à trancher avant la
mise en production (`SMS_PROVIDER=unconfigured` échoue explicitement en
attendant).

**Rate limiting** sur `request-otp` (par numéro et par IP), et de la même
façon sur le triage IA, les documents et les photos de profil : fenêtre
glissante (`app/services/rate_limit.py`). En staging/prod, les compteurs
vivent dans la table `rate_limit_hit` (`RATE_LIMIT_BACKEND=postgres`, par
défaut hors dev) : **partagés par toutes les instances et conservés au
redémarrage**. Chaque vérification tourne dans sa propre transaction
(un appel refusé ensuite reste décompté), un verrou consultatif par clé
empêche N requêtes simultanées de dépasser la limite, et la clé (numéro,
IP, utilisateur) n'est jamais stockée en clair -- seulement son empreinte
SHA-256. Base indisponible = requête refusée (échec fermé). En dev, l'état
reste en mémoire pour simplifier.

## Lecture des artisans (recherche géo, avis, stats)

`GET /api/v1/artisans` (proximité PostGIS, filtres `trade`/`min_rating`/
`available`/`q`, tri `distance`/`rating`/`recent`, pagination), `GET
/api/v1/artisans/{id}` (profil détaillé), `GET /api/v1/artisans/{id}/reviews`
(avis publiés), `GET /api/v1/artisans/{id}/stats` (indicateurs de réputation
publics ; revenus réservés au propriétaire ou à un admin authentifié), `GET
/api/v1/trades` (référentiel des métiers). Aucune authentification requise
sauf pour la vue enrichie de `/stats`. Détail complet (combinaison rayon
client/zone artisan, stratégie de pagination, règle de dérivation de
`verified_status`) : [BUILD_PLAN.md §5](../BUILD_PLAN.md#5-architecture-géo-postgis)
et [§2.2](../BUILD_PLAN.md#22-tables).

**Architecture en couches** (`app/api/v1/`, `app/services/`,
`app/repositories/`, `app/schemas/`) instaurée sur ce lot, appliquée à
`trades` et `artisans` -- gabarit pour le reste du projet. `app/api/v1/auth.py`
n'a volontairement pas été réaligné dessus (flux déjà propre et testé,
réalignement recommandé dans un lot dédié séparé si souhaité).

## Onboarding artisan (profil, métiers, documents)

`PATCH /api/v1/artisans/me` (artisan authentifié, mise à jour partielle --
seuls les champs fournis sont appliqués) édite `full_name`, `bio`,
`years_experience`, `base_location`, `avatar_url`, `cover_url`,
`is_available`. `verified_status` et le rôle n'y apparaissent jamais : le
premier reste toujours dérivé, le second n'est modifiable par aucun
endpoint. `POST /api/v1/artisans/me/trades` /
`DELETE /api/v1/artisans/me/trades/{id}` déclarent/retirent un métier
exercé (tarif indicatif, rayon ou polygone de zone d'intervention).

**Photos du profil public** (avatar, couverture) : `POST
/api/v1/artisans/me/avatar` et `POST /api/v1/artisans/me/cover`
(`multipart/form-data`, champ `file`). Données PUBLIQUES, servies sous
`/static/avatars` -- jamais le stockage privé des documents ci-dessous.
JPEG/PNG vérifiés par magic bytes, taille plafonnée, budget d'envois
**partagé** entre les deux routes (`429 TROP_DE_DEMANDES` au-delà).
**Jamais servies telles quelles** (`app/services/image_processing.py`) :
chaque image est entièrement décodée (un fichier à signature valide mais
non décodable est refusé), ses métadonnées EXIF -- dont la **position GPS**
de la prise de vue -- sont retirées après application de l'orientation,
elle est redimensionnée (`AVATAR_MAX_SIDE_PX` / `COVER_MAX_SIDE_PX`) puis
recompressée (JPEG, ou PNG si transparence). Les dimensions sont plafonnées
avant décodage (`PROFILE_MEDIA_MAX_PIXELS`, `422 IMAGE_DIMENSIONS_EXCESSIVES`).
Les documents de vérification, eux, ne sont jamais retouchés. Au
remplacement, l'ancien fichier n'est effacé qu'**après le commit** et
seulement si sa clé appartient prouvablement au profil courant et au bon
type de média (`app/services/profile_media.py`) -- une URL collée à la main
via `PATCH` (http(s) absolu uniquement) ne fait jamais effacer le fichier
de quelqu'un d'autre.

**Documents de vérification** (CNI, selfie) : `POST /api/v1/artisans/me/documents`
(`multipart/form-data`, `doc_type` + `file`), `GET .../documents` (métadonnées
seules -- jamais le binaire), `GET .../documents/{id}/content` (le binaire,
propriétaire uniquement, jamais un lien public). Le **type réel du fichier
est vérifié par ses magic bytes** (`app/services/file_validation.py`),
jamais par l'extension ni le `Content-Type` déclaré -- les deux se
falsifient trivialement. Le fichier est stocké sous un identifiant aléatoire
via une **couche d'abstraction** (`Protocol StorageBackend`,
`app/services/storage.py`, même principe que `SmsProvider`/
`AiTriageProvider`) : `LocalStorageBackend` (dev) écrit hors du dépôt git et
hors de tout répertoire servi statiquement ; un fournisseur cloud privé
reste à brancher avant la prod, sans réécrire le code appelant.

Chaque document déposé recrée/actualise la ligne `verification`
correspondante et **recalcule immédiatement `artisan_profile.verified_status`**
(`app/services/verification.compute_verified_status`) : `NONE -> PENDING`
dès le premier document soumis, `VERIFIED` seulement quand tous les types
requis (`VERIFICATION_REQUIRED_DOC_TYPES`) sont à `approved` -- ce qui
n'arrive qu'après revue humaine (espace admin, voir section dédiée
ci-dessous).

**Éligibilité à la mise en relation.** Un artisan `verified_status !=
VERIFIED` (1) est rejeté par `POST /api/v1/interventions`
(`ARTISAN_NON_VERIFIE`, déjà en place depuis le Lot 12) et (2) **n'apparaît
pas** dans `GET /api/v1/artisans` (recherche publique) -- décision actée,
justifiée dans `app.services.artisans.list_artisans`. `GET
/api/v1/artisans/{id}` reste accessible quel que soit le statut : c'est ce
qui permet à l'artisan de voir son propre profil pendant son onboarding.

## Espace admin (revue des artisans)

Toutes les routes `/api/v1/admin/*` exigent le rôle `admin`
(`require_role(Role.ADMIN)`) -- voir [Bootstrap du premier
admin](#bootstrap-du-premier-admin) ci-dessus pour la seule façon d'obtenir
ce rôle. Un client/artisan reçoit `403 ROLE_INSUFFISANT`, un anonyme `401`
-- les mêmes erreurs génériques que n'importe quelle autre route protégée
par rôle, sans détail qui distinguerait une route admin pour un tiers non
autorisé.

`GET /api/v1/admin/verifications?status=pending` : file d'attente de revue,
triée du plus ancien document déposé au plus récent (FIFO), filtrable par
statut (défaut `pending`). `GET .../verifications/{id}/content` : le
binaire du document, via la même couche de stockage privée que l'onboarding
artisan (jamais un lien public) -- réservé admin, pas seulement au
propriétaire du document. `POST .../verifications/{id}/approve` et
`.../reject` (`{ note }`, obligatoire, ≥ 3 caractères) tranchent un
document `pending` : `reviewed_by`/`reviewed_at` sont posés côté serveur
depuis l'admin authentifié (JWT), jamais un champ d'entrée. Chaque décision
recalcule immédiatement `artisan_profile.verified_status`
(`compute_verified_status`) -- une approbation complète (tous les types
requis à `approved`) rend l'artisan visible en recherche publique et
contactable ; un document déjà tranché ne se re-tranche pas
(`VERIFICATION_DEJA_TRAITEE`, 409). `GET /admin/artisans/{id}` : vue admin
d'un artisan (profil + historique complet de ses documents, contrairement
au profil public qui n'en expose aucun) pour décider en contexte.

Frontend : `/admin/verifications`, hors `MainLayout` (outil interne, pas
d'identité "client"/"Espace Pro"). `RequireAdminRoute`
(`src/components/auth/`) affiche l'écran 404 standard pour tout compte
non-admin -- jamais un message "accès refusé" ni une redirection vers
`/connexion`, l'un comme l'autre confirmeraient l'existence de la section.
Aucun lien vers `/admin/*` n'apparaît dans la navigation pour un compte
non-admin.

## Triage IA (Lot 11)

`POST /api/v1/ai/analyze { description }` migre l'ancien `/api/analyze-problem`
(Express + Gemini) vers FastAPI, **provider-agnostique** : le reste du code ne
connaît que le `Protocol AiTriageProvider` (`app/services/ai_triage_providers.py`),
jamais un fournisseur concret.

- **Fournisseurs** : `HeuristicTriageProvider` (mots-clés français, aucun
  appel réseau, toujours disponible -- filet de secours et défaut sûr) et
  `MistralTriageProvider` (API Mistral, sortie JSON forcée via
  `response_format: json_object`, timeout explicite). Sélection par
  `AI_TRIAGE_PROVIDER` (voir tableau des variables ci-dessus) -- même
  principe que `SMS_PROVIDER`.
- **Durcissement de la sortie** (`app/services/ai_triage.py`) : la réponse
  du fournisseur réseau est validée par un schéma Pydantic strict
  (`TriageResult` -- montants positifs, `total_fcfa == labor_fcfa +
  materials_fcfa`, `urgency` dans l'enum fermé) **et** son `trade_code` doit
  référencer un métier actif de la table `trade`. À la moindre anomalie
  (timeout, erreur HTTP, JSON malformé, schéma non conforme, métier
  inconnu/inactif) : rejet + bascule automatique sur l'heuristique, incident
  loggé -- **jamais de mapping approximatif vers le métier "le plus proche"**,
  et jamais d'erreur 500 renvoyée au client pour un incident IA (durcissement
  demandé par l'audit du Lot 0 sur l'ancien endpoint, qui ne validait rien).
- **Accès** : public, non authentifié (l'écran `/demande` du front n'exige
  pas de connexion) mais protégé par rate limiting par IP, fenêtre glissante
  en mémoire -- même mécanisme et même dette technique que
  `RATE_LIMIT_OTP_*` (voir [Authentification](#authentification-téléphone--otp)
  ci-dessus). Chaque appel routé vers un fournisseur réseau coûte
  potentiellement de l'argent réel, d'où la protection même quand le
  fallback heuristique (gratuit) finit par répondre.
- **Portée** : ce lot couvre uniquement l'analyse (`POST /ai/analyze`). La
  persistance de la demande (`POST /requests`) et l'upload photo réel
  restent hors périmètre (BUILD_PLAN.md §6, note de portée du Lot 11).
  L'Express `/api/analyze-problem` reste en place (retrait prévu au Lot 13)
  mais n'est plus appelé par le front.

**Vérification manuelle** (nécessite une vraie clé Mistral) :

1. Dans `backend/.env` : `MISTRAL_API_KEY=<votre clé>` et
   `AI_TRIAGE_PROVIDER=mistral`, puis redémarrer le serveur.
2. `POST /api/v1/ai/analyze` avec une description réelle (ex. `{"description":
   "ma robinetterie fuit sous l'évier"}`) -- via `/docs`, `curl`, ou l'écran
   `/demande` du front. Vérifier un `trade_code` cohérent (`plomberie`), un
   `price_min_fcfa`/`price_max_fcfa` réaliste, et `suggested_quote.total_fcfa
   == labor_fcfa + materials_fcfa`.
3. Couper la clé (`MISTRAL_API_KEY=` vide) ou repasser
   `AI_TRIAGE_PROVIDER=heuristic`, redémarrer, rejouer la même requête :
   vérifier qu'une réponse `200` cohérente est toujours renvoyée (jamais
   d'erreur), signe que le fallback fonctionne.
4. (Optionnel, pour observer le fallback en conditions réelles) fournir une
   clé invalide avec `AI_TRIAGE_PROVIDER=mistral` : vérifier une réponse
   `200` malgré tout (fallback heuristique) et un log `WARNING` mentionnant
   l'échec du fournisseur.

## Porte de validation

Commande unique (ruff check, ruff format --check, mypy strict, pytest) :

```bash
uv run python scripts/validate.py
```
