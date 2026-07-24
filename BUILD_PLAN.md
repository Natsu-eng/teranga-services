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
| is_available | bool | toggle dispo |
| verified_status | enum(`none`,`pending`,`verified`,`rejected`) | dérivé des `verification`, **pas** un booléen |
| subscription_tier | enum(`free`,`verified`) | monétisation (abonnement) |
| created_at / updated_at / deleted_at | | |

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
POST /api/v1/auth/request-otp     { phone }                    → 204
POST /api/v1/auth/verify-otp      { phone, code }              → { access, refresh, user }
POST /api/v1/auth/refresh         { refresh }                  → { access }
GET  /api/v1/auth/me                                           → user courant
```

**Artisans**
```
GET  /api/v1/artisans             ?trade=&near=lat,lng&radius=&min_rating=&available=
                                   → liste triée par distance (PostGIS)
GET  /api/v1/artisans/{id}                                     → profil + stats + réalisations
GET  /api/v1/artisans/{id}/reviews                             → avis publiés
GET  /api/v1/artisans/{id}/stats                               → revenus, note, taux réponse
PATCH /api/v1/artisans/me         (artisan) { bio, availability, trades… }
```

**Demandes & IA**
```
POST /api/v1/requests             (client) { trade?, description, photo?, location, urgency }
POST /api/v1/ai/analyze           { description }  → { trade, price_range, urgency, suggested_quote }
                                   (migration de /api/analyze-problem, provider-agnostique)
GET  /api/v1/requests/me                                       → mes demandes
```

**Interventions, devis, avis**
```
POST /api/v1/interventions        (issue d'une demande + artisan)  → fige commission_rate
POST /api/v1/interventions/{id}/quote      (artisan) { labor, materials }
POST /api/v1/interventions/{id}/quote/accept (client)
POST /api/v1/interventions/{id}/complete   → completed_at, ouvre l'avis
POST /api/v1/interventions/{id}/review     (client, si terminée) { rating, comment }
```

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

---

## 5. Architecture géo (PostGIS)

- Colonnes `geography(Point/Polygon, 4326)`.
- « Artisans près de moi » = `ST_DWithin(base_location, :point, :radius)` + tri
  par `ST_Distance`. Index **GiST** sur les colonnes géo (indispensable perf).
- Le front envoie `near=lat,lng&radius=` ; il utilisera `navigator.geolocation`
  réel (aujourd'hui simulé par un sélecteur de quartier).

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
- **Lot 9 — Lecture artisans + géo.** `GET /artisans` (filtres + PostGIS),
  `/artisans/{id}`, stats, avis. *But : le front peut lire du vrai.*
- **Lot 10 — Bascule du front.** Implémentation `http` de la couche `api` du
  Lot 4, bascule `mock → http` (un seul point), gestion loading/erreur déjà en
  place. *But : le front parle à FastAPI.*
- **Lot 11 — Demandes + IA migrée.** `POST /requests`, upload photo réel,
  migration de `/analyze-problem` vers `/ai/analyze` **provider-agnostique**
  (Gemini aujourd'hui, swappable). *But : l'IA vit dans FastAPI.*
- **Lot 12 — Interventions, devis, avis** (entonnoir + commission figée + avis
  conditionné). *But : le cœur métier et la monétisation.*
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
