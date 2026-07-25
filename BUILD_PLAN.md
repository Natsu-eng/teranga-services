# BUILD_PLAN — Téranga Services (Phase 2 : Backend)

> Document de référence de la Phase 2. Il cadre le backend FastAPI, le modèle de
> données PostgreSQL/PostGIS, les contrats d'API, l'authentification et la
> stratégie de monétisation. Il est vivant : on le met à jour à chaque lot.
>
> **Principe directeur** : on construit nous-mêmes, de bout en bout, en
> s'inspirant des meilleures pratiques SaaS. Rien en dur, tout typé, tout testé,
> un lot = une intention, validé avant de continuer.

---

## 0. État à la fin de la Phase 1 (frontend)

Acquis, ne pas refaire :

- Frontend React 19 + TypeScript strict, Tailwind v4 (design tokens `@theme`).
- Navigation par React Router 7 (URLs réelles, deep-linking, 404, fallback SPA).
- **Couche d'accès aux données** `src/lib/api/` : interface + implémentation `mock`
  asynchrone. **C'est le point de bascule unique vers HTTP.** Les écrans ne
  connaissent que l'interface, jamais l'implémentation.
- Données 100 % mock (`src/data/mockData.ts`), aucune persistance.
- Un seul endpoint réel : `POST /api/analyze-problem` (Express + Gemini, avec
  fallback heuristique).
- Porte de validation : `npm run validate` (typecheck + lint + test).

**Cible Phase 2** : remplacer le mock par un vrai backend FastAPI + Postgres,
brancher le front dessus via la couche `api`, faire disparaître Express une fois
la migration complète.

---

## 1. Décisions d'architecture (actées)

| Sujet | Décision | Raison |
|---|---|---|
| Langage backend | **Python + FastAPI** | Stack maîtrisée, async natif, typage Pydantic, OpenAPI auto |
| Base de données | **PostgreSQL + PostGIS** | Géo natif (« artisans près de moi »), robustesse, gratuit |
| ORM | **SQLAlchemy 2.x** (mode async) | Standard, typé, mûr |
| Migrations | **Alembic** | Migrations versionnées, réversibles, obligatoires |
| Validation | **Pydantic v2** | Schémas d'API stricts, une seule source de vérité |
| Base en dev | **Postgres local (pgAdmin)** | Gratuit, rapide, jetable ; `DATABASE_URL` unique |
| Base en prod | **Railway** (managé) | Bascule = 1 variable d'env, zéro code |
| Topologie | **2 services séparés** : front (Vite) + API (FastAPI) | Standard SaaS, déploiement propre, front délocalisable (Vercel) |
| Sort d'Express | **Condamné, en douceur** | FastAPI monte à côté, on migre l'IA, puis Express dégage |
| Auth | **Téléphone + OTP** (SMS) | Standard Sénégal ; corrige le `userRole` auto-déclarable |
| Secrets | **Jamais en dur** | Tout via variables d'environnement (`.env`, jamais commité) |

### Règle d'or config

Une seule variable `DATABASE_URL`. Local aujourd'hui :
```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/teranga
```
Railway demain : on change **cette ligne**, rien d'autre.

---

## 2. Modèle de données PostgreSQL

Issu du benchmark (Wecasa, StarOfService, Checkatrade, TaskRabbit) et de la
littérature sur la **désintermédiation** (la fuite hors plateforme croît avec le
taux de commission). Chaque table anticipe un risque produit réel.

### 2.1 Vue d'ensemble

```
user ──1:1── artisan_profile ──1:N── verification
 │              │        │
 │              │        └──1:N── artisan_trade (métier + zone d'intervention géo)
 │              │
 │              └──1:N── review  ◄──── intervention ────► service_request
 │                                        │                     │
 └──1:N── service_request ───────────────┘                     │
                                                                │
 intervention ──1:1── quote (devis)                             │
      │                                                         │
      ├──1:N── payment ──► platform_fee (découplée)             │
      │                                                         │
      └──1:N── payout (versement artisan)                       │
                                                                │
 commission_rate (versionnée, dates d'effet) ◄─ figée sur l'intervention
 conversation ──1:N── message ◄── liée à service_request/intervention
 otp_code ──► user (auth)
 user ──1:N── refresh_token (sessions JWT, rotation + révocation)

 trade (table de référence) ◄── artisan_trade.trade_id
                             ◄── service_request.trade_id
                             ◄── commission_rate.trade_id
```

### 2.2 Tables

Conventions : `id` en UUID, `created_at`/`updated_at` en `timestamptz`,
suppression logique (`deleted_at`) là où l'historique compte. Montants en
**entiers FCFA** (jamais de flottant sur de l'argent).

> **Métiers (`trade`) : table de référence, pas un enum.** Les métiers
> s'ajoutent en continu (nouvel artisanat, nouvelle ville) sans jamais
> justifier une migration de schéma, et l'i18n Wolof est prévue sur leur
> libellé. Toute colonne qui référence un métier est donc une FK
> `trade_id → trade.id`, jamais un enum en dur.
>
> **Statuts et énumérations fermées** (`role`, `verified_status`,
> `subscription_tier`, `doc_type`, `urgency`, les colonnes `status`, `channel`,
> `kind`, `locale`) : implémentés en `Enum(native_enum=False)` côté
> SQLAlchemy — c'est-à-dire une colonne `VARCHAR` + une contrainte `CHECK` côté
> base, avec un enum Python côté code applicatif. Un type enum PostgreSQL
> natif ne se modifie pas proprement (ajouter/retirer une valeur est une
> opération DDL délicate) et Alembic ne supprime pas le type au downgrade,
> ce qui casserait la réversibilité des migrations.

#### `trade` (table de référence)
Le métier exercé par un artisan (ou demandé par un client). Table, pas un
enum : voir encadré ci-dessus.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| code | text unique | ex. `plomberie`, `electricite` — identifiant stable, jamais affiché |
| label_fr | text | libellé affiché (FR) |
| label_wo | text null | libellé Wolof — préparé, pas encore alimenté (i18n hors périmètre Phase 2, cf. §8) |
| icon | text null | identifiant d'icône côté front |
| sort_order | int | ordre d'affichage dans les listes/filtres |
| is_active | bool | permet de retirer un métier du catalogue sans le supprimer |

#### `user`
Compte de base, commun client et artisan.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| phone | text unique | E.164, ex. `+221771234567` — identifiant de connexion |
| phone_verified_at | timestamptz null | posé après OTP réussi |
| full_name | text | |
| role | enum(`client`,`artisan`,`admin`) | **vérifié serveur**, plus jamais un toggle client |
| locale | enum(`fr`,`wo`) | défaut `fr` |
| created_at / updated_at | timestamptz | |
| deleted_at | timestamptz null | |

> **Sécurité** : le rôle vit ici, côté serveur, contrôlé à chaque requête. C'est
> la correction du point d'audit « n'importe qui peut s'auto-déclarer artisan ».

#### `artisan_profile`
Extension 1:1 d'un `user` de rôle `artisan`.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → user unique | |
| bio | text | |
| years_experience | int | |
| base_location | geography(Point,4326) | domicile/atelier (PostGIS) |
| avatar_url / cover_url | text | |
| is_available | bool | toggle dispo — modifiable via `PATCH /artisans/me` (Lot 12c) |
| verified_status | enum(`none`,`pending`,`verified`,`rejected`) | dérivé des `verification`, **pas** un booléen — voir encadré ci-dessous |
| subscription_tier | enum(`free`,`verified`) | monétisation (abonnement) |
| rating_avg | numeric(3,2) null | **dénormalisé** depuis `review` (avis `publie` uniquement) — recalculé par `recalculate_artisan_rating`, jamais saisi (Lot 9) |
| review_count | int, défaut 0 | idem, dénormalisé et recalculé avec `rating_avg` |
| created_at / updated_at / deleted_at | | |

> **`verified_status` : règle de dérivation exacte** (`app.services.verification.compute_verified_status`,
> Lot 9). Soit `REQUIRED` l'ensemble des `doc_type` requis (Settings
> `VERIFICATION_REQUIRED_DOC_TYPES`, défaut `cni,selfie`) :
>
> 1. Aucune ligne `verification` du tout → **NONE**.
> 2. Pour chaque type de `REQUIRED`, ne retenir que la ligne la plus récente
>    (`created_at` max) — un artisan peut resoumettre après un rejet.
> 3. Tous les types de `REQUIRED` ont leur dernière ligne à `approved` → **VERIFIED**.
> 4. Sinon, au moins un type de `REQUIRED` est absent (rien soumis) ou `pending` → **PENDING**.
> 5. Sinon (au moins un type de `REQUIRED` `rejected`, rien en attente) → **REJECTED**.
>
> La colonne `verified_status` existe en base mais n'est **jamais lue telle
> quelle** par la couche de lecture : les endpoints chargent les
> `verification` (eager load) et appellent cette fonction à la volée. Elle
> reste néanmoins tenue à jour à l'écriture (seed, et futur lot de
> vérification admin) pour ne jamais diverger inutilement de la valeur
> dérivée.
>
> **Dénormalisation `rating_avg`/`review_count`** : un `AVG(rating)` par
> artisan sur chaque requête de liste ne tient pas à l'échelle.
> `app.services.reviews.recalculate_artisan_rating` recalcule les deux
> colonnes depuis les avis `publie` uniquement (masqué/signalé exclus),
> appelée après toute mutation d'un avis (insertion ou changement de statut).

#### `verification`
Documents de vérification d'un artisan. **Plusieurs par artisan** (CNI, selfie,
accréditation métier), avec statut — inspiré directement de Checkatrade.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| artisan_id | UUID FK → artisan_profile | |
| doc_type | enum(`cni`,`selfie`,`accreditation`,`address_proof`) | |
| doc_url | text | stockage privé (pas public) |
| status | enum(`pending`,`approved`,`rejected`) | |
| reviewed_by | UUID FK → user null | admin qui a statué |
| reviewed_at | timestamptz null | |
| note | text null | motif de rejet éventuel |
| created_at | timestamptz | |

#### `artisan_trade`
Un artisan peut exercer plusieurs métiers, chacun avec sa zone d'intervention.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| artisan_id | UUID FK → artisan_profile | |
| trade_id | UUID FK → trade | |
| hourly_rate_fcfa | int | tarif indicatif |
| service_radius_m | int | rayon d'intervention en mètres |
| service_area | geography(Polygon,4326) null | zone précise si définie (PostGIS) |

#### `service_request`
Demande d'un client (le point d'entrée de l'entonnoir).

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| client_id | UUID FK → user | |
| trade_id | UUID FK → trade | métier détecté/choisi |
| description | text | |
| photo_url | text null | photo jointe (réellement uploadée en Phase 2) |
| location | geography(Point,4326) | où intervenir |
| urgency | enum(`normal`,`urgent`,`immediat`) | |
| ai_estimate_min_fcfa / ai_estimate_max_fcfa | int null | fourchette IA |
| status | enum(`ouverte`,`en_relation`,`convertie`,`annulee`,`expiree`) | |
| created_at / updated_at | | |

#### `intervention`
Le cœur de l'entonnoir : une mise en relation qui devient un travail réel.
**C'est l'ancre de la commission, des avis et des paiements.**

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| service_request_id | UUID FK → service_request | |
| client_id | UUID FK → user | |
| artisan_id | UUID FK → artisan_profile | |
| status | enum(`proposee`,`acceptee`,`en_cours`,`terminee`,`annulee`,`litige`) | |
| commission_rate_id | UUID FK → commission_rate | **taux figé à la création** |
| agreed_amount_fcfa | int null | montant convenu (via devis) |
| scheduled_at | timestamptz null | |
| completed_at | timestamptz null | déclenche l'éligibilité à l'avis |
| created_at / updated_at | | |

#### `quote` (devis)
1:1 avec une intervention (le devis accepté la matérialise).

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| intervention_id | UUID FK → intervention unique | |
| labor_fcfa | int | main d'œuvre |
| materials_fcfa | int | matériaux |
| total_fcfa | int | = labor + materials (contrôlé serveur) |
| status | enum(`propose`,`accepte`,`refuse`,`expire`) | |
| created_at | timestamptz | |

#### `commission_rate` (versionnée)
**Le taux n'est JAMAIS en dur.** Table de tarifs avec dates d'effet. Le taux
appliqué à une intervention passée reste figé (comptabilité, litiges, confiance).

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| rate_bps | int | en points de base (1000 = 10,00 %) — **défaut 1000** |
| trade_id | UUID FK → trade null | null = tous métiers |
| tier | enum(`free`,`verified`) null | granularité par palier possible |
| effective_from | timestamptz | date d'effet |
| effective_to | timestamptz null | null = en vigueur |
| created_at | timestamptz | |

> **Amorçage** : on peut insérer un `rate_bps = 0` sur les 3 premiers mois, puis
> `rate_bps = 1000` (10 %) ensuite, sans aucune migration de schéma.
> Décision produit actée : **10 % par défaut** (sous Wecasa 25 %, sous TaskRabbit 15 %).

#### `payment`
Un encaissement. **Le canal inclut le cash** — sinon on ne mesure pas la fuite.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| intervention_id | UUID FK → intervention | |
| amount_fcfa | int | |
| channel | enum(`wave`,`orange_money`,`free_money`,`carte`,`cash`) | cash enregistrable |
| status | enum(`en_attente`,`reussi`,`echoue`,`rembourse`) | |
| provider_ref | text null | id transaction opérateur/agrégateur |
| wave_event_id | text null unique | **idempotence** (Wave retente 5× sur 24 h) |
| paid_at | timestamptz null | |
| created_at / updated_at | | |

#### `platform_fee`
Ce que Téranga prélève, **découplé du paiement** : permet abonnement, lead OU
commission sans refonte.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| intervention_id | UUID FK → intervention null | null si abonnement pur |
| kind | enum(`commission`,`subscription`,`lead`) | |
| amount_fcfa | int | |
| commission_rate_id | UUID FK → commission_rate null | traçabilité du taux appliqué |
| status | enum(`due`,`collectee`,`annulee`) | |
| created_at | timestamptz | |

#### `payout`
Versement à l'artisan. **Le versement rapide est le meilleur rempart anti-cash.**

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| artisan_id | UUID FK → artisan_profile | |
| intervention_id | UUID FK → intervention | |
| amount_fcfa | int | net après platform_fee |
| channel | enum(`wave`,`orange_money`,`bank`) | |
| status | enum(`en_attente`,`envoye`,`echoue`) | |
| provider_ref | text null | |
| sent_at | timestamptz null | |
| created_at | timestamptz | |

#### `review`
Avis **conditionné à une intervention terminée** + contact vérifié (SMS).
C'est la digue anti-faux-avis de Checkatrade (90 % de leurs avis sont vérifiés).

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| intervention_id | UUID FK → intervention unique | 1 avis / intervention |
| author_id | UUID FK → user | le client |
| artisan_id | UUID FK → artisan_profile | |
| rating | int (1–5) | |
| comment | text | |
| contact_verified | bool | client vérifié par SMS |
| status | enum(`publie`,`masque`,`signale`) | modération |
| created_at | timestamptz | |

> **Règle métier** : un `review` ne peut exister que si l'`intervention` liée est
> `terminee`. Contrainte applicative + idéalement contrainte DB.

#### `conversation` / `message`
Messagerie liée à une demande/intervention. Base pour la détection de fuite
(Phase 3+ : NLP sur partage de numéros hors plateforme).

| `conversation` | Type |
|---|---|
| id | UUID PK |
| service_request_id | UUID FK null |
| intervention_id | UUID FK null |
| client_id / artisan_id | UUID FK → user |
| created_at | timestamptz |

| `message` | Type |
|---|---|
| id | UUID PK |
| conversation_id | UUID FK → conversation |
| sender_id | UUID FK → user |
| body | text |
| kind | enum(`texte`,`devis`,`systeme`) |
| created_at | timestamptz |

#### `otp_code` (auth)
Codes OTP pour la connexion par téléphone.

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| phone | text | |
| code_hash | text | **haché**, jamais en clair |
| expires_at | timestamptz | TTL court (ex. 5 min) |
| consumed_at | timestamptz null | usage unique |
| attempts | int | anti-bruteforce |
| created_at | timestamptz | |

#### `refresh_token` (auth, Lot 8)
Sessions de refresh JWT, persistées. **Ajout non prévu à l'origine dans ce
document** : sans cette table, un refresh token volé reste valide jusqu'à
expiration (jusqu'à 30 jours) sans qu'on puisse ni déconnecter un appareil
précis, ni couper un compte compromis. La persistance permet la **rotation**
(chaque `/refresh` révoque l'ancien token et en émet un nouveau) et la
**révocation** (`/logout`, `/logout-all`, et la révocation de toute la
famille si un token déjà révoqué est rejoué — signal de vol).

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK → user | |
| token_hash | text | **haché**, jamais en clair |
| jti | UUID unique | identifiant du JWT (claim `jti`), indexé |
| expires_at | timestamptz | miroir de l'`exp` du JWT |
| revoked_at | timestamptz null | posé à la révocation (logout, rotation, vol détecté) |
| created_at | timestamptz | |
| user_agent | text null | contexte de l'appareil, pour affichage futur des sessions actives |
| ip | text null | contexte de connexion, pour audit |

---

## 3. Contrats d'API (FastAPI)

Préfixe : `/api/v1`. Réponses en JSON, erreurs normalisées. Auth par JWT court +
refresh. Tous les schémas en Pydantic v2 (une seule source de vérité, OpenAPI
généré automatiquement à `/docs`).

### 3.1 Format d'erreur normalisé
```json
{ "error": { "code": "ARTISAN_NOT_FOUND", "message": "Artisan introuvable." } }
```
`message` en français, prêt à afficher (cohérent avec `ApiError` du front, Lot 4).

### 3.2 Endpoints (cible Phase 2, par lot)

**Auth**
```
POST /api/v1/auth/request-otp     { phone }                    → 204 (systématique, non énumérant)
POST /api/v1/auth/verify-otp      { phone, code }              → { access, refresh, user }
POST /api/v1/auth/refresh         { refresh }                  → { access, refresh } (rotation)
POST /api/v1/auth/logout          { refresh }                  → 204 (révoque ce token)
POST /api/v1/auth/logout-all      (authentifié)                → 204 (révoque toutes les sessions)
GET  /api/v1/auth/me              (authentifié)                → user courant
```
`phone` est normalisé en E.164 (§4) avant toute recherche ou écriture ;
`/refresh` révoque systématiquement l'ancien token (rotation) — voir §4 pour
le comportement en cas de rejeu d'un token déjà révoqué. Depuis le Lot 12,
`user` (`verify-otp`, `/me`) porte aussi `artisan_profile_id` (`null` pour un
client ou un artisan sans profil) : ferme le lien `user <-> artisan_profile`
qu'un placeholder front (`artisanId = user.id`) comblait jusque-là
(AUDIT_PHASE2.md §6).

**Artisans** (Lot 9 — lecture publique, sauf mention contraire)
```
GET  /api/v1/artisans             ?trade=&near=lat,lng&radius_m=&min_rating=&available=&q=
                                   &sort=distance|rating|recent&page=&page_size=
                                   → { items: [...], pagination: {...} }, triée par distance si
                                     `near` fourni (défaut rating sinon)
GET  /api/v1/artisans/{id}                                     → profil détaillé (métiers,
                                   verified_status dérivé, note), sans coordonnées/contact
GET  /api/v1/artisans/{id}/reviews                             → avis publiés (status=publie), paginés
GET  /api/v1/artisans/{id}/stats                               → indicateurs de réputation (public,
                                   sans auth) ; + revenus si authentifié en tant que propriétaire ou
                                   admin (403 STATISTIQUES_PRIVEES_INTERDITES pour un tiers authentifié)
GET  /api/v1/trades                                            → référentiel des métiers actifs
PATCH /api/v1/artisans/me         (artisan) { is_available }                                  ✅ Lot 12c
                                   -- bascule sa propre disponibilité, scopée à son
                                   artisan_profile (résolu depuis le token). Volontairement
                                   limité à ce seul champ ; l'édition complète (bio, métiers,
                                   zone) reste hors périmètre, reportée à l'onboarding artisan.
```
Erreurs normalisées spécifiques : `POSITION_INVALIDE` (near malformé/hors
bornes), `RAYON_RECHERCHE_INVALIDE` (radius_m ≤0 ou > plafond),
`TRI_DISTANCE_SANS_POSITION` (sort=distance sans near), `PAGE_HORS_BORNES`
(page au-delà du plafond dur), `ARTISAN_NOT_FOUND` (404),
`STATISTIQUES_PRIVEES_INTERDITES` (403). Détail de la recherche géo et de
la pagination : §5.

**Demandes & IA**
```
POST /api/v1/requests             (client) { trade_code, description, photo_url?, location, urgency,
                                   ai_estimate_min_fcfa?, ai_estimate_max_fcfa? }             ✅ Lot 12
GET  /api/v1/requests/me                                       → mes demandes, paginé         ✅ Lot 12
GET  /api/v1/requests/{id}        (propriétaire ou artisan concerné)                          ✅ Lot 12
POST /api/v1/ai/analyze           { description }
                                   → { trade_code, price_min_fcfa, price_max_fcfa, urgency,
                                        suggested_quote: { labor_fcfa, materials_fcfa, total_fcfa } }
                                   (migration de /api/analyze-problem, provider-agnostique —
                                   Mistral par défaut, fallback heuristique, §6 Lot 11)
```

`POST /ai/analyze` est **public, non authentifié** (l'écran `/demande` du
front n'exige pas de connexion) mais protégé par rate limiting par IP (même
mécanisme que `/auth/request-otp`, `TROP_DE_DEMANDES` en cas de dépassement)
: chaque appel routé vers un fournisseur réseau coûte potentiellement de
l'argent réel. La sortie du fournisseur IA est strictement validée
(montants, cohérence du total, énumération d'urgence fermée) et son
`trade_code` doit référencer un métier actif de la table `trade` — sinon,
rejet et bascule silencieuse sur l'heuristique, jamais d'erreur 500 pour un
incident IA. Détail complet des fournisseurs et de la logique de fallback :
`backend/app/services/ai_triage.py` et `ai_triage_providers.py`.
`POST /requests` (persistance de la demande), différé par le Lot 11, est
maintenant couvert par la première moitié du Lot 12 (§6) : `ai_estimate_min_fcfa`/
`ai_estimate_max_fcfa` sont acceptés en entrée mais **re-validés côté serveur**
(`app.services.requests._validate_ai_estimate`) — jamais fait confiance
aveuglément à ce que le client transmet.

**Interventions, devis, avis**
```
POST /api/v1/interventions        (client, issue d'une demande + artisan) → fige               ✅ Lot 12
                                   commission_rate_id (résolu par app.services.commission :
                                   le plus spécifique métier > global, en vigueur à l'instant T)
GET  /api/v1/interventions/me     (vue adaptée au rôle client/artisan)                         ✅ Lot 12
GET  /api/v1/interventions/{id}   (client ou artisan concernés)                                ✅ Lot 12
POST /api/v1/interventions/{id}/accept     (artisan concerné) proposee -> acceptee             ✅ Lot 12
POST /api/v1/interventions/{id}/decline    (artisan concerné) proposee -> annulee,             ✅ Lot 12
                                   motif optionnel, la service_request redevient ouverte
POST /api/v1/interventions/{id}/quote      (artisan, intervention acceptee) { labor_fcfa,      ✅ Lot 12
                                   materials_fcfa } → total calculé serveur ; un seul devis
                                   actif, un re-devis remplace le précédent (contrainte 1:1)
POST /api/v1/interventions/{id}/quote/accept (client) → intervention en_cours,                 ✅ Lot 12
                                   agreed_amount_fcfa renseigné
POST /api/v1/interventions/{id}/quote/refuse (client) → l'artisan peut re-deviser              ✅ Lot 12
POST /api/v1/interventions/{id}/complete   (client uniquement) en_cours -> terminee            ✅ Lot 12
POST /api/v1/interventions/{id}/review     (client, si terminée) { rating, comment } →         ✅ Lot 12
                                   recalcule rating_avg/review_count de l'artisan
```
Règles vérifiées à la création d'une intervention (`app.services.interventions.create_intervention`) :
demande `ouverte` et possédée par le client courant, artisan existant et
`verified_status == VERIFIED`, exerçant le métier de la demande, et dont la
zone d'intervention (réutilise la logique rayon/zone géo du Lot 9, §5.1)
couvre la position de la demande — sinon rejet normalisé
(`DEMANDE_AUTRUI_INTERDITE`, `DEMANDE_NON_OUVERTE`, `ARTISAN_NON_VERIFIE`,
`ARTISAN_METIER_NON_EXERCE`, `ARTISAN_HORS_ZONE`).

**Machine à états de l'intervention** (`app.services.interventions.transition_intervention`,
seule porte d'entrée pour muter `intervention.status`, BUILD_PLAN.md §6 Lot 12b) :
```
proposee --(artisan accepte)--> acceptee --(devis accepté)--> en_cours --(complétion)--> terminee
proposee --(artisan refuse)--> annulee
```
Toute autre transition renvoie `TRANSITION_INTERVENTION_INVALIDE` (409).
`litige` n'a aucune transition entrante/sortante gérée à ce stade.

Le devis est un objet autonome (`quote`, 1:1 avec `intervention`) jamais un
message de chat — la messagerie (à venir) le référencera sans le contenir.
Total toujours calculé serveur, jamais reçu du client. Un re-devis après
refus remplace physiquement la ligne existante (`quote.intervention_id` est
UNIQUE en base, Lot 7) plutôt que d'en empiler une seconde.

**Qui déclenche la complétion : le client, seul.** Un artisan ne peut jamais
clôturer unilatéralement une intervention dont il est juge et partie
(éligibilité à la commission et à l'avis) ; un aller-retour "l'artisan
signale, le client confirme" exigerait un statut intermédiaire absent du
modèle de données actuel — le client seul est le compromis retenu pour ce
lot, sans conflit d'intérêt.

L'avis (`POST /interventions/{id}/review`) est revalidé côté service
(`AVIS_INTERVENTION_NON_TERMINEE`, erreur normalisée claire) en plus du
trigger PostgreSQL `review_requires_completed_intervention` (Lot 7, dernier
rempart) — jamais l'erreur DB brute renvoyée au client.

**Paiements (Phase 2 tardive)**
```
POST /api/v1/payments/init        { intervention_id, channel } → wave_launch_url / instructions
POST /api/v1/webhooks/wave        (HMAC-SHA256 vérifié, idempotent via wave_event_id)
```

**Messagerie**
```
GET  /api/v1/conversations/{id}/messages
POST /api/v1/conversations/{id}/messages   { body }
```

---

## 4. Authentification (téléphone + OTP)

Flux : `request-otp` (génère code, hache, envoie SMS) → `verify-otp` (compare
hash, marque `phone_verified_at`, renvoie JWT access court + refresh) → requêtes
authentifiées via `Authorization: Bearer`.

Garde-fous : TTL 5 min, usage unique (`consumed_at`), compteur `attempts` avec
blocage, rate-limit par téléphone et par IP. En dev, provider SMS *mock* (log du
code en console) ; en prod, provider réel (à choisir : agrégateur SMS local).

**Le rôle est porté par le serveur** (`user.role`), vérifié à chaque requête par
une dépendance FastAPI. Fin définitive du `userRole` auto-déclarable côté client.
Aucun endpoint ne permet à un utilisateur de modifier son propre rôle : le
passage à `artisan` se fera via la création d'un `artisan_profile` (lot
métier), et `admin` ne s'attribue que hors application (script/SQL direct).

### 4.1 Normalisation E.164 du téléphone (Lot 8)

Le téléphone est l'identifiant de connexion (`user.phone`) : sans normalisation,
`"77 123 45 67"`, `"0771234567"` et `"+221771234567"` créeraient trois comptes
distincts pour le même numéro. Toute écriture ou recherche passe donc par une
normalisation canonique **avant** d'atteindre la base : `user.phone` ne stocke
que la forme E.164. Implémentée via la bibliothèque `phonenumbers` (pas de
regex maison), indicatif par défaut Sénégal (`+221`), configurable via env
(`PHONE_DEFAULT_REGION`, `PHONE_ALLOWED_REGIONS`) pour préparer
l'internationalisation. Un numéro invalide ou d'un pays non autorisé est
rejeté explicitement (erreur en français), avant toute requête base.

### 4.2 Sessions JWT et rotation du refresh (Lot 8)

Access token court (défaut 15 min) + refresh token long (défaut 30 jours),
signés HS256 avec un secret obligatoire (`JWT_SECRET`, fail-fast au démarrage
si absent ou trop court — même principe que `DATABASE_URL` au Lot 6). Payload :
`sub`, `role`, `jti`, `iat`, `exp`.

Le refresh est **persisté** (table `refresh_token`, §2.2) : à chaque
`POST /auth/refresh`, l'ancien token est révoqué et un nouveau émis
(rotation). Si un refresh **déjà révoqué** est présenté, c'est le signal d'un
vol (rejeu d'un token volé après que le titulaire légitime a déjà tourné) :
**toute la famille de refresh tokens de l'utilisateur est révoquée**, forçant
une reconnexion complète sur tous les appareils.

---

## 5. Architecture géo (PostGIS)

- Colonnes `geography(Point/Polygon, 4326)`.
- « Artisans près de moi » = `ST_DWithin(base_location, :point, :radius)` + tri
  par `ST_Distance`. Index **GiST** sur les colonnes géo (indispensable perf).
- Le front envoie `near=lat,lng&radius=` ; il utilisera `navigator.geolocation`
  réel (aujourd'hui simulé par un sélecteur de quartier).

### 5.1 Combinaison rayon client / zone artisan (Lot 9)

`GET /api/v1/artisans` combine **deux contraintes géo indépendantes**, en ET
logique — un artisan n'apparaît que si les deux tiennent :

1. **Rayon de recherche du client** (`near` + `radius_m`) : pertinence pour
   *cette* recherche — `ST_DWithin(base_location, near, radius_m)`.
2. **Zone d'intervention de l'artisan** (par `artisan_trade`, celui filtré si
   `trade` est fourni, sinon n'importe lequel via un `EXISTS` corrélé) :
   capacité opérationnelle réelle de l'artisan, indépendamment de la
   recherche du client — si `service_area` (polygone) est défini,
   `ST_Covers(service_area, near)` (PostGIS ne supporte `ST_Contains`/
   `ST_Within` qu'en `geometry`, pas `geography` — `ST_Covers` est le bon
   choix) ; sinon `ST_DWithin(base_location, near, service_radius_m)`.

Exemple concret : un artisan à 2 km d'un client mais dont la zone
d'intervention ne couvre pas ce point est exclu, même si le client cherche
dans un rayon de 20 km — et réciproquement, un artisan à 9 km reste exclu si
son propre `service_radius_m` (5 km par défaut) ne l'atteint pas, même si le
rayon de recherche du client est large. Cette combinaison est appliquée
**systématiquement**, y compris sans `near`/`trade` actifs : un artisan sans
aucun `artisan_trade` n'apparaît jamais dans une recherche.

Tri : `sort=distance|rating|recent`. `near` absent → tri par défaut `rating`
sans échouer. `near` présent sans `sort` explicite → tri par défaut
`distance`. `sort=distance` explicite sans `near` → erreur normalisée
(`TRI_DISTANCE_SANS_POSITION`). Tri `rating` avec `NULLS LAST` explicite
(Postgres met les artisans jamais notés en tête en `DESC` par défaut). Un
tie-breaker `id` est appliqué sur les 3 modes de tri pour une pagination
déterministe.

### 5.2 Pagination (Lot 9)

Stratégie retenue : **offset borné**, pas de curseur composite. Justifiée
par trois modes de tri dynamiques (distance/rating/recent) qui rendraient un
curseur composite coûteux à maintenir pour un bénéfice marginal à l'échelle
d'un marché artisan (résultat déjà borné par le filtre géo — centaines de
lignes, pas de millions), et une UI de découverte qui veut des numéros de
page, pas un scroll infini. Réutilisée par `GET /artisans` et
`GET /artisans/{id}/reviews` via une enveloppe générique
(`{ items, pagination: { page, page_size, total, total_pages } }`).

Plafond dur **non contournable** : une page au-delà de
`PAGINATION_MAX_PAGE` est rejetée explicitement (`422 PAGE_HORS_BORNES`),
jamais clampée silencieusement. Une page au-delà du nombre réel de résultats
mais dans les bornes autorisées reste `200` avec `items: []`. `page_size`
est clampé silencieusement à `PAGINATION_PAGE_SIZE_MAX` (pas d'erreur — seul
le plafond de `page` est un rejet dur).

---

## 6. Séquence des lots (Phase 2)

Chaque lot = branche dédiée, commits atomiques, `validate` vert, revue avant
merge. Le backend a sa propre porte (`pytest`, `ruff`, `mypy`).

- **Lot 6 — Socle backend.** Repo/dossier `backend/`, FastAPI, SQLAlchemy async,
  Alembic, connexion Postgres locale via `DATABASE_URL`, healthcheck, config
  typée (Pydantic Settings), qualité (ruff + mypy + pytest), 1 table de test qui
  migre. *But : le squelette tourne de bout en bout.*
- **Lot 7 — Modèle de données complet.** Tous les modèles SQLAlchemy + migration
  Alembic initiale + PostGIS activé + seed de dev (les 3 artisans du mock, en
  vraies lignes). *But : la base reflète ce document.*
- **Lot 8 — Auth OTP.** Endpoints auth, JWT, dépendance de rôle, provider SMS
  mock en dev. *But : sécurité réelle, fin du rôle auto-déclaré.*
- **Lot 9 — Lecture artisans + géo.** ✅ `GET /artisans` (filtres + proximité
  PostGIS, combinant rayon client et zone d'intervention artisan, §5.1),
  `/artisans/{id}`, `/artisans/{id}/reviews`, `/artisans/{id}/stats`
  (indicateurs publics + revenus réservés au propriétaire/admin),
  `GET /trades`. Architecture en couches `api → services → repositories →
  schemas` instaurée (nouveau dossier `app/repositories/`), pagination
  offset bornée (§5.2), `verified_status` dérivé et `rating_avg`/
  `review_count` dénormalisés (§2.2). *But : le front peut lire du vrai.*
- **Lot 10 — Bascule du front.** Implémentation `http` de la couche `api` du
  Lot 4, bascule `mock → http` (un seul point), gestion loading/erreur déjà en
  place. *But : le front parle à FastAPI.*
- **Lot 11 — IA migrée.** ✅ Migration de `/analyze-problem` (Express + Gemini)
  vers `POST /api/v1/ai/analyze` **provider-agnostique** (`Protocol
  AiTriageProvider`, Mistral par défaut derrière `AI_TRIAGE_PROVIDER`,
  fallback heuristique sans réseau), sortie strictement validée (schéma,
  montants, `trade_code` vérifié contre la table `trade`), rate limiting par
  IP. Le front (`DescribeProblemScreen`) est basculé dessus. *Portée réduite
  par rapport à l'intention initiale de ce lot* : `POST /requests` (persistance
  de la demande) et l'upload photo réel restent hors périmètre, reportés à un
  lot ultérieur (candidat naturel : Lot 12, en même temps que le reste de
  l'entonnoir) — les relier à `service_request.ai_estimate_min_fcfa`/
  `ai_estimate_max_fcfa` (§2.2) à ce moment-là. *But : l'IA vit dans FastAPI.*
- **Lot 12 — Interventions, devis, avis** (entonnoir + commission figée + avis
  conditionné). *But : le cœur métier et la monétisation.*
  - **Première moitié ✅ (`feat/requests-interventions`) : demandes et mise en
    relation.** `POST /api/v1/requests` (persistance, `ai_estimate_min_fcfa`/
    `ai_estimate_max_fcfa` acceptés mais re-validés côté serveur — referme la
    portée différée du Lot 11), `GET /requests/me`, `GET /requests/{id}`
    (propriétaire ou artisan concerné). `POST /api/v1/interventions` : figeage
    du `commission_rate_id` (résolu par `app.services.commission`, le plus
    spécifique métier > global, en vigueur à l'instant `T` — jamais recalculé
    ensuite), avec la séquence complète de garde-fous (demande `ouverte` et
    possédée par le client, artisan vérifié, exerçant le métier, couvrant
    géographiquement la position — réutilise la géo du Lot 9), `GET
    /interventions/me` (vue adaptée au rôle client/artisan, base du futur
    dashboard artisan), `GET /interventions/{id}`. `GET /auth/me` expose
    désormais `artisan_profile_id` (ferme le lien `user <-> artisan_profile`,
    AUDIT_PHASE2.md §6). Front : `/demande` crée réellement une
    `service_request` avec le `trade_code` détecté par l'IA (fin du matching
    factice sur un artisan fixe) et redirige vers `/recherche` filtrée
    côté serveur (`trade`, `near`) ; écran `/mes-demandes` (client). *Portée
    différée à la seconde moitié de ce lot* : `quote` (devis), `review`
    (écriture, conditionnée à `intervention.status = terminee`),
    `conversation`/`message` — aucun endpoint pour ces domaines n'existe
    encore.
  - **Seconde moitié ✅ (`feat/quotes-reviews`) : cycle de vie complet,
    devis, avis.** Machine à états centralisée
    (`app.services.interventions.transition_intervention`, seule porte
    d'entrée pour muter `intervention.status` : `proposee -> acceptee ->
    en_cours -> terminee`, `proposee -> annulee`, toute autre transition
    rejetée `TRANSITION_INTERVENTION_INVALIDE`). `POST
    /interventions/{id}/accept|decline` (artisan concerné ; refuser rouvre la
    `service_request`, migration `f35086f6d699` pour `decline_reason`).
    `POST /interventions/{id}/quote` (artisan, intervention `acceptee`,
    total calculé serveur, un seul devis actif — un re-devis remplace
    l'ancien plutôt que de l'empiler, `quote.intervention_id` étant UNIQUE en
    base). `POST /interventions/{id}/quote/accept|refuse` (client).
    `POST /interventions/{id}/complete` (client seul — un artisan ne clôture
    jamais unilatéralement). `POST /interventions/{id}/review` (client
    propriétaire, `terminee` revalidée côté service en plus du trigger DB
    Lot 7, recalcule `rating_avg`/`review_count` via
    `app.services.reviews.recalculate_artisan_rating`, Lot 9). Front : écran
    d'interventions partagé client/artisan (`InterventionsScreen`/
    `InterventionCard`, piloté par rôle + statut), monté sur `/pro` (premier
    vrai contenu de l'espace Artisan Pro, remplace le placeholder "Bientôt
    disponible") et sur la nouvelle route cliente `/mes-interventions`.
    *Portée différée* : `conversation`/`message` (messagerie) restent hors
    périmètre — aucun endpoint pour ce domaine n'existe encore.
  - **Troisième partie ✅ (`feat/artisan-dashboard`) : vrai dashboard artisan
    sur `/pro`.** `PATCH /api/v1/artisans/me { is_available }` (artisan
    uniquement, scopé à son propre `artisan_profile` résolu depuis le token
    — jamais reçu du client ; portée volontairement limitée à ce seul champ,
    l'édition complète du profil artisan est un chantier d'onboarding
    ultérieur). `GET /artisans/{id}/stats` : revenus dérivés des `payment`
    réussis liés aux interventions de l'artisan (`revenue_fcfa` sera 0 pour
    tout artisan tant que le Lot 14 — paiements — n'est pas construit,
    aucun `payment` ne peut encore être créé par l'API ; c'est une valeur
    réellement dérivée, pas un placeholder en dur, juste une source encore
    vide), `interventions_count` (interventions `terminee`), `rating_avg`/
    `review_count` (dénormalisés, Lot 9), `response_rate` (toujours `null`,
    aucun tracking `responded_at` n'existe). Front : `ArtisanDashboardScreen`
    remplace l'écran d'interventions nu sur `/pro` — en-tête distincte
    (fond `bg-primary` sombre, identité "Espace Pro") avec le toggle de
    disponibilité (optimiste, rollback si le PATCH échoue), les cartes de
    stats (hook `useArtisanStats`, orphelin depuis le Lot 9, enfin branché
    — `httpApiClient` n'implémentait pas `getArtisanStats`, le hook
    retombait silencieusement sur des données mock fictives, AUDIT_PHASE2.md
    §6), et les demandes de l'artisan regroupées par statut (nouveau
    composant partagé `InterventionsList`, extrait d'`InterventionsScreen`
    pour éviter la duplication, utilisé flat sur `/mes-interventions` et
    groupé ici). `BottomNav` artisan : "Demandes"/"Revenus" (deux liens vers
    le même `/pro`, AUDIT_PHASE2.md §6) fusionnés en une seule entrée
    "Tableau de bord".
- **Lot 13 — Retrait d'Express.** Une fois l'IA et tout le reste migrés, Express
  et `server.ts` sont supprimés (preuve grep). *But : un seul backend.*
- **Lot 14 — Paiements** (Wave Business API : checkout, webhook HMAC idempotent,
  payout) + **Lot 15 — Déploiement Railway** (2 services + Postgres managé,
  bascule `DATABASE_URL`). *À séquencer selon priorités.*

---

## 7. Monétisation (rappel des décisions)

- **Hybride, pas commission pure.** Abonnement « Vérifié » (revenu récurrent,
  indépendant du canal de paiement) + commission **10 %** par défaut.
- **Pas de lead-gen payant** tant que la qualité du lead n'est pas garantie
  (leçon StarOfService : facturer un mauvais lead détruit la confiance artisan).
- **Taux jamais en dur** : `commission_rate` versionnée, figée sur l'intervention.
- **Anti-désintermédiation** (la fuite croît avec le taux) : messagerie in-app,
  versement rapide à l'artisan, re-réservation facile, avis vérifiés, cash
  *enregistrable* pour le mesurer.

---

## 8. Ce qui reste hors périmètre Phase 2 (noté pour plus tard)

Scoring de fiabilité des artisans, détection de fuite par NLP sur la messagerie,
assistant conversationnel, i18n Wolof/Français, tarification dynamique,
notifications push. Phase 3+.
