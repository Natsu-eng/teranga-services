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
| Sort d'Express | **Retiré (Lot 13)** ✅ | FastAPI a pris l'IA (Lot 11) puis tout le reste ; le front est un projet Vite pur |
| Auth | **Téléphone + OTP** (SMS) | Standard Sénégal ; corrige le `userRole` auto-déclarable |
| Secrets | **Jamais en dur** | Tout via variables d'environnement (`.env`, jamais commité) |

### Service du front (depuis le Lot 13)

- **Dev** : deux process — `uvicorn` (backend, port 8000) et `vite` (front,
  port 3000 fixe). Le front appelle `/api/v1` en relatif ; le proxy natif de
  Vite (`frontend/vite.config.ts`, cible `BACKEND_URL`) le route vers FastAPI.
- **Production** : `vite build` → fichiers statiques (`dist/`) servis par
  l'hébergeur, fallback SPA compris (`frontend/vercel.json`). Le navigateur
  appelle le backend via `VITE_API_BASE_URL` (URL absolue, figée au build),
  l'origine du front étant autorisée par `CORS_ORIGINS` côté backend — ou,
  variante, `/api/v1` même-origine derrière un reverse proxy.
- **En-têtes de sécurité** du front (CSP, `X-Frame-Options: DENY`,
  `nosniff`, `Referrer-Policy`, `Permissions-Policy`) définis une seule fois
  dans `vercel.json` et rejoués par `vite preview` pour les tester en local.
- **Aucun secret côté front** : la seule configuration IA est celle du
  backend (`AI_TRIAGE_PROVIDER`, `MISTRAL_API_KEY`).

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
| cancelled_at / cancelled_by / cancellation_kind / cancellation_reason | null | clôture d'une intervention `annulee` : quand, par qui (`client`/`artisan`/`admin`), comment (`refus`, `annulation`, `arbitrage`), motif ; ensemble ou absents (CHECK). Remplacent `decline_reason` (lot `feat/paiements`) |
| created_at / updated_at | | |

#### `intervention_dispute` (litige, lot `feat/paiements`)
Un problème signalé sur des travaux en cours **gèle l'argent** jusqu'à la
décision d'un admin (§3.5).

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| intervention_id | UUID FK → intervention **unique** | un litige par intervention |
| opened_by_id / opened_by_role | UUID FK → user / enum | client ou artisan |
| reason | text | obligatoire (10 caractères min. côté API) |
| outcome | enum(`libere`,`rembourse`) null | décision de l'admin |
| resolved_by_id / resolved_at / resolution_note | null | renseignés avec `outcome` (CHECK) |
| created_at | timestamptz | ouverture |

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
| status | enum(`en_attente`,`retenu`,`libere`,`reussi`,`echoue`,`annule`,`rembourse`) | cycle de vie §3.5 |
| provider | text null | fournisseur (`sandbox`, ...) ; NULL **ssi** cash (CHECK) |
| provider_ref | text null | référence du checkout ; unique par fournisseur |
| checkout_url / checkout_expires_at | null | page de paiement hébergée et son expiration |
| paid_at / released_at / refunded_at | timestamptz null | reçu (séquestre) / libéré / remboursé |
| refund_ref | text null | référence du remboursement |
| created_at / updated_at | | |

**Au plus un paiement vivant par intervention** (`en_attente`, `retenu`,
`libere`, `reussi`) : index unique partiel `uq_payment_active_intervention_id`.
`wave_event_id` (propre à un fournisseur, un seul événement par paiement)
est remplacé par la table `payment_event`.

#### `payment_event` (lot `feat/paiements`)
Journal des webhooks reçus. **Clé d'idempotence** : `(provider, event_id)`
unique — une notification rejouée n'est jamais retraitée (§3.5).

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| provider / event_id | text | unique ensemble |
| event_type | text | type brut du fournisseur (audit) |
| payment_id | UUID FK → payment null | null si paiement inconnu |
| outcome | text | `retenu`, `echoue`, `deja_traite`, `paiement_inconnu`, `montant_incoherent`, `rembourse_paiement_tardif`, `ignore` |
| received_at | timestamptz | |

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
| status | enum(`due`,`collectee`,`annulee`) | `collectee` = déduite du séquestre ; `due` en cash = due par l'artisan |
| settled_at | timestamptz null | passage à `collectee`/`annulee` |
| created_at | timestamptz | |

Une seule commission par intervention (index unique partiel sur
`kind = 'commission'`), montant calculé **une fois** sur le taux figé et
stocké : changer la règle d'arrondi ne réécrit jamais le passé.

#### `payout`
Versement à l'artisan. **Le versement rapide est le meilleur rempart anti-cash.**

| Champ | Type | Notes |
|---|---|---|
| id | UUID PK | |
| artisan_id | UUID FK → artisan_profile | |
| intervention_id | UUID FK → intervention | |
| amount_fcfa | int | net après platform_fee |
| channel | enum(`wave`,`orange_money`,`bank`) | |
| status | enum(`en_attente`,`envoye`,`echoue`) | `echoue` relançable (`scripts/dispatch_payouts.py`) |
| destination_phone | text | **numéro vérifié (OTP) du compte artisan**, copié pour l'audit — jamais saisi |
| provider / provider_ref | text | fournisseur et référence du versement |
| attempts / last_attempt_at / failure_reason | | tentatives et dernier échec |
| sent_at | timestamptz null | |
| created_at | timestamptz | |

Un seul versement par intervention (`uq_payout_intervention_id`).
`artisan_profile.payout_channel` (null = `PAYOUT_DEFAULT_CHANNEL`) : le
moyen choisi par l'artisan, jamais la destination.

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
Messagerie in-app client ↔ artisan, **une conversation par intervention**,
créée avec l'intervention (lot `feat/messagerie`, §3.4). Le masquage des
coordonnées est le premier filet anti-fuite ; la détection par NLP reste en
Phase 3+.

| `conversation` | Type |
|---|---|
| id | UUID PK |
| service_request_id | UUID FK null (historique, non utilisé par la messagerie) |
| intervention_id | UUID FK null — **unique** quand renseigné (index partiel `uq_conversation_intervention_id`) |
| client_id / artisan_id | UUID FK → user (les deux SEULS participants ; `artisan_id` = le compte de l'artisan) |
| client_last_read_seq / artisan_last_read_seq | bigint ≥ 0 — curseur de lecture de chaque partie (ne recule jamais) |
| last_message_at | timestamptz null — tri par activité (`clock_timestamp()`, pas `now()`) |
| created_at | timestamptz |

| `message` | Type |
|---|---|
| id | UUID PK |
| conversation_id | UUID FK → conversation |
| sender_id | UUID FK → user |
| seq | bigint identity **unique**, croissant — curseur de synchronisation (`since`/`before`), index `(conversation_id, seq)` |
| body | text — **déjà masqué** : le numéro d'origine n'est jamais stocké |
| contact_masked | bool — un numéro/e-mail a été masqué (affiché aux deux parties) |
| attachment_key / attachment_content_type | text / varchar(64) null — photo jointe, stockage privé (§3.4) |
| kind | enum(`texte`,`devis`,`systeme`) |
| created_at | timestamptz |

Contraintes : `body_or_attachment` (jamais de message vide), `attachment_complete`
(clé et type renseignés ensemble). Migration `c0a26cec109e` (réversible) :
ajoute ces colonnes et ouvre la conversation des interventions existantes.

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
POST /api/v1/auth/verify-otp      { phone, code, intent,        → { access, refresh, user }
                                     role? }
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
(AUDIT_PHASE2.md §6). Depuis le lot `feat/auth-signup`, `verify-otp` porte
`intent` (`login`|`signup`) et `role` (`client`|`artisan`, requis en
signup) : détail complet en §4.3.

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
PATCH /api/v1/artisans/me         (artisan) { is_available?, bio?, years_experience?,           ✅ Lot 12c
                                   base_location?, avatar_url?, cover_url? }              ✅ onboarding artisan
                                   -- avatar_url/cover_url : URL http(s) absolue
                                   uniquement (422 sinon), chaîne vide = retirer.
                                   -- édite son propre artisan_profile (résolu depuis le
                                   token), mise à jour PARTIELLE (seuls les champs fournis
                                   sont appliqués). Ne touche jamais verified_status (dérivé)
                                   ni le rôle -- absents du schéma d'entrée.
POST /api/v1/artisans/me/avatar   (artisan) multipart/form-data { file }              ✅ onboarding artisan
                                   -- upload de la photo de profil (JPEG/PNG, magic
                                   bytes). Donnée PUBLIQUE (contrairement aux
                                   documents ci-dessous) : stockage dédié, servi via
                                   /static/avatars. avatar_url renvoyé est une URL
                                   ABSOLUE (BACKEND_PUBLIC_BASE_URL) -- front et back
                                   sont deux services séparés en prod (§1). L'ancien
                                   fichier est supprimé au remplacement (best-effort).
                                   PATCH /artisans/me (ci-dessus) accepte toujours
                                   avatar_url en texte libre en complément (coller un
                                   lien externe), les deux chemins écrivent le même champ.
POST /api/v1/artisans/me/cover    (artisan) multipart/form-data { file }              ✅ feat/profile-media
                                   -- photo de couverture : même régime PUBLIC, même
                                   stockage et mêmes garde-fous que l'avatar (taille
                                   COVER_MAX_UPLOAD_BYTES). Budget d'envois PARTAGÉ avec
                                   /me/avatar (429 TROP_DE_DEMANDES au-delà).
POST /api/v1/artisans/me/trades   (artisan) { trade_code, hourly_rate_fcfa,           ✅ onboarding artisan
                                   service_radius_m, service_area? } -- déclare un métier
                                   exercé. Rejette un trade_code inconnu/inactif
                                   (METIER_INTROUVABLE) ou déjà déclaré
                                   (ARTISAN_METIER_DEJA_DECLARE).
DELETE /api/v1/artisans/me/trades/{id}                                                ✅ onboarding artisan
                                   -- retire un métier déclaré, scopé au propriétaire
                                   (ARTISAN_TRADE_NOT_FOUND sinon, jamais 403 distinctif).
POST /api/v1/artisans/me/documents (artisan) multipart/form-data { doc_type, file }    ✅ onboarding artisan
                                   -- upload d'un document de vérification (cni|selfie|
                                   accreditation|address_proof). Type réel validé par magic
                                   bytes (jamais extension/Content-Type déclarés), taille
                                   plafonnée (STORAGE_MAX_UPLOAD_BYTES), clé de stockage
                                   aléatoire (jamais le nom de fichier d'origine), rate limité
                                   par utilisateur. Crée/actualise la verification en
                                   `pending` et recalcule immédiatement
                                   artisan_profile.verified_status. Détail sécurité et
                                   couche de stockage : §3.3.
GET  /api/v1/artisans/me/documents (artisan)                                          ✅ onboarding artisan
                                   → { verified_status, documents: [...] } -- métadonnées
                                   seules (doc_type, status, note, dates), jamais le binaire
                                   ni doc_url.
GET  /api/v1/artisans/me/documents/{id}/content (artisan, propriétaire uniquement)     ✅ onboarding artisan
                                   → le binaire du document, servi via la couche de stockage
                                   (jamais un lien statique public). DOCUMENT_NOT_FOUND pour
                                   un document d'un autre artisan (jamais de distinction
                                   observable entre "absent" et "pas à vous").
```
**Visibilité en recherche publique (`GET /artisans`)** : un artisan dont
`verified_status != VERIFIED` est **invisible** de cette liste (filtré en
SQL sur la colonne stockée, tenue à jour à chaque écriture de
`verification`) -- décision actée, justifiée en détail dans
`app.services.artisans.list_artisans` (en résumé : un profil non vérifié
n'apporte aucune valeur à un client qui ne pourra de toute façon pas le
contacter, et un catalogue 100 % vérifié est un signal de confiance plus
fort au lancement). `GET /artisans/{id}` **n'applique pas** ce filtre :
l'artisan doit pouvoir voir son propre profil pendant l'onboarding quel que
soit son statut.
Erreurs normalisées spécifiques : `POSITION_INVALIDE` (near malformé/hors
bornes), `RAYON_RECHERCHE_INVALIDE` (radius_m ≤0 ou > plafond),
`TRI_DISTANCE_SANS_POSITION` (sort=distance sans near), `PAGE_HORS_BORNES`
(page au-delà du plafond dur), `ARTISAN_NOT_FOUND` (404),
`STATISTIQUES_PRIVEES_INTERDITES` (403). Détail de la recherche géo et de
la pagination : §5.

**Demandes & IA**
```
POST /api/v1/requests             (client) { trade_code, description, photo_url?, location,
                                   location_label?, urgency,
                                   ai_estimate_min_fcfa?, ai_estimate_max_fcfa? }             ✅ Lot 12
GET  /api/v1/requests/me                                       → mes demandes, paginé         ✅ Lot 12
GET  /api/v1/requests/me/eligibility?artisan_id=   (client)    → pour chaque demande ouverte :
                                   { request_id, eligible, reason } (lecture seule)
GET  /api/v1/artisans/{id}/coverage?trade=&lat=&lng=  (public) → { eligible, reason } pour un
                                   lieu, avant même de créer la demande (lecture seule)
GET  /api/v1/requests/{id}        (propriétaire ou artisan concerné)                          ✅ Lot 12
POST /api/v1/ai/analyze           { description }
                                   → { trade_code, price_min_fcfa, price_max_fcfa, urgency,
                                        suggested_quote: { labor_fcfa, materials_fcfa, total_fcfa } }
                                   (migration de /api/analyze-problem, provider-agnostique —
                                   Mistral par défaut, fallback heuristique, §6 Lot 11)
```

**Localisation explicite (lot `fix/localisation-demande`).** Le lieu d'une
demande est celui que le client a **vu et confirmé** : un quartier (liste
unique `frontend/src/lib/places.ts`, coordonnées réelles, partagée avec
l'en-tête) ou sa position GPS, proposée seulement sur demande et appliquée
après confirmation. `location_label` le garde lisible. La règle
d'engagement côté artisan (vérifié, métier exercé, zone d'intervention) est
une fonction **unique** (`evaluate_engagement`) : `POST /interventions`
l'applique et refuse toujours (`ARTISAN_HORS_ZONE`, dernier rempart) ; les
deux lectures ci-dessus l'exposent pour que l'écran marque « hors de sa
zone » AVANT l'envoi — le marquage ne peut pas diverger de la décision.

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

**Paiements** ✅ (lot `feat/paiements`, détail §3.5)
```
GET  /api/v1/payments/options             (client) → moyens réellement proposés
POST /api/v1/payments/init                { intervention_id, channel } (client propriétaire)
                                    → résumé financier + checkout_url (en ligne) ;
                                      AUCUN montant accepté : celui du devis accepté
GET  /api/v1/payments/me                  (client) → ses paiements
GET  /api/v1/payments/me/earnings         (artisan) → versé, séquestre, commissions,
                                      espèces, commission due + détail
GET|PUT /api/v1/payments/me/payout-settings  (artisan) { channel } → moyen de versement,
                                      destination = numéro vérifié du compte
POST /api/v1/webhooks/payments            public, signé HMAC, idempotent (payment_event)
POST /api/v1/interventions/{id}/cancel    { reason? } (client tant que rien n'est en
                                      séquestre ; artisan après acceptation)
POST /api/v1/interventions/{id}/dispute   { reason } (client ou artisan, en_cours)
GET  /api/v1/admin/disputes               ?resolved=  (admin)
POST /api/v1/admin/disputes/{id}/resolve  { outcome: libere|rembourse, note } (admin)
GET|POST /api/v1/sandbox/checkout/{jeton} page de paiement simulée (sandbox seulement)
```
Le résumé financier (`payment` : total, commission au taux figé, net,
statuts, versement) voyage dans `InterventionOut`, lisible par les deux
parties et l'admin seulement (`GET /interventions/{id}` : tiers -> 403).
`decline_reason` est remplacé par `cancellation` (kind, by, reason, at).

**Messagerie** ✅ (lot `feat/messagerie`, détail §3.4) — client ou artisan
participant uniquement ; admin exclu (`403 ROLE_INSUFFISANT`).
```
GET  /api/v1/conversations/me              ?page=&page_size=&artisan_id=
                                    → mes discussions, triées par activité,
                                      dernier message et non-lus de chacune
GET  /api/v1/conversations/me/unread-count → { count } (badge de navigation)
GET  /api/v1/conversations/{id}            → contexte (interlocuteur, intervention,
                                      can_send, my_last_read_seq)
GET  /api/v1/conversations/{id}/messages   ?since=<seq> | ?before=<seq>, &limit=
                                    → historique ; `since` sert au rattrapage
                                      et au repli polling
POST /api/v1/conversations/{id}/messages   { body }        → 201 (texte masqué)
POST /api/v1/conversations/{id}/messages/image  multipart file (+ caption)
                                    → 201 ; photo réencodée, EXIF/GPS retirés
GET  /api/v1/conversations/{id}/messages/{message_id}/attachment
                                    → binaire, participants seuls,
                                      Cache-Control: private, no-store
POST /api/v1/conversations/{id}/read       { last_read_seq } → curseur avancé
POST /api/v1/realtime/ticket               → { ticket, expires_in } (60 s, usage unique)
WS   /api/v1/realtime/ws                   sous-protocoles ["teranga.v1", "ticket.<jwt>"]
```
Conversation inexistante OU d'autrui : même `403 CONVERSATION_ACCES_INTERDIT`
(l'existence d'un fil n'est jamais révélée). Demande annulée :
`409 CONVERSATION_FERMEE` à l'envoi (lecture toujours possible).

**Admin** (espace admin -- toutes les routes exigent `require_role(Role.ADMIN)`,
BUILD_PLAN.md §4.4 ; un client/artisan reçoit 403 ROLE_INSUFFISANT, un
anonyme 401, exactement les mêmes erreurs génériques que n'importe quelle
autre route protégée par rôle)
```
GET  /api/v1/admin/verifications   ?status=pending|approved|rejected      ✅ espace admin
                                    (défaut pending)&page=&page_size=
                                    → file d'attente de revue, triée du plus
                                      ancien document déposé au plus récent (FIFO)
GET  /api/v1/admin/verifications/{id}/content                            ✅ espace admin
                                    → le binaire du document, via la même couche
                                      de stockage privée que Lot B (jamais d'URL
                                      publique) -- réservé admin, pas seulement
                                      au propriétaire du document
POST /api/v1/admin/verifications/{id}/approve                            ✅ espace admin
                                    → passe la ligne verification à `approved`,
                                      reviewed_by = l'admin authentifié (JWT,
                                      jamais un champ d'entrée), reviewed_at
                                      horodaté serveur ; recalcule
                                      immédiatement artisan_profile.verified_status
POST /api/v1/admin/verifications/{id}/reject     { note }                ✅ espace admin
                                    → idem, à `rejected` ; `note` obligatoire
                                      (min 3 caractères) -- jamais de rejet muet,
                                      l'artisan la voit dans son espace (Lot B)
GET  /api/v1/admin/artisans/{id}                                         ✅ espace admin
                                    → vue admin d'un artisan : profil + TOUS ses
                                      documents (historique complet, contrairement
                                      à ArtisanDetailOut public qui n'en expose
                                      aucun) -- pour décider en contexte
```
Un document déjà tranché (`approved`/`rejected`) ne se re-tranche pas :
`VERIFICATION_DEJA_TRAITEE` (409) si un admin tente d'approuver/rejeter une
ligne qui n'est plus `pending` -- protège contre une double décision sur une
ligne devenue obsolète (l'artisan a pu déjà renvoyer un nouveau document du
même type après un rejet, seule la ligne la plus récente par type comptant
pour `compute_verified_status`, §2.2).

---

## 3.3 Stockage de fichiers privés (onboarding artisan)

Les documents de vérification (CNI, selfie) sont des **données sensibles** :
jamais servis publiquement, jamais commités en git, accès strictement
réservé à l'artisan propriétaire (et, plus tard, à l'admin qui statue,
Lot C). Même principe d'abstraction que `SmsProvider`
(`app/services/sms.py`) et `AiTriageProvider`
(`app/services/ai_triage_providers.py`) : un `Protocol StorageBackend`
(`app/services/storage.py`) que le code métier (`app.services.documents`)
manipule sans jamais connaître son implémentation concrète.

```python
class StorageBackend(Protocol):
    async def store(self, content: bytes, key: str) -> str: ...    # -> référence opaque
    async def retrieve(self, reference: str) -> bytes: ...
    async def delete(self, reference: str) -> None: ...
```

**`LocalStorageBackend`** (seul fournisseur implémenté, dev) écrit sur
disque local sous `STORAGE_LOCAL_DIR` (défaut `backend/var/artisan-documents`,
relatif au dossier `backend/`) : hors du code source applicatif, ignoré par
`backend/.gitignore`, jamais monté en `StaticFiles` (`app/main.py` ne sert
aucun fichier statique — tout accès passe par `GET
/artisans/me/documents/{id}/content`, authentifié et scopé au propriétaire).
Le contenu est manipulé en `bytes` (pas un vrai flux asynchrone) : choix
délibéré, les documents concernés sont petits et plafonnés en taille
(`STORAGE_MAX_UPLOAD_BYTES`) — bufferiser en mémoire garde le backend
trivial sans complexité de streaming pour un cas d'usage borné ; le client
HTTP reçoit malgré tout une réponse en flux (`StreamingResponse` côté
endpoint).

**Bascule vers un cloud privé en prod** (S3-compatible à accès privé, GCS…) :
n'implique qu'une nouvelle classe respectant ce même `Protocol`, branchée
via `STORAGE_BACKEND=<nom>` (`Settings`, jamais en dur) — aucune réécriture
du code appelant. Aucun fournisseur cloud n'est implémenté à ce stade
(`STORAGE_BACKEND=local` est la seule valeur acceptée aujourd'hui ; toute
autre valeur lève `NotImplementedError` au démarrage de l'accès, même
principe fail-fast documenté que `SMS_PROVIDER=unconfigured`) — ce choix
reste à trancher avant la mise en production, le disque local de
`LocalStorageBackend` ne survivant de toute façon pas à un redéploiement
Railway (pas de disque persistant).

**Upload sécurisé** (`POST /artisans/me/documents`,
`app.services.documents.upload_document`) :
1. **Type réel validé par magic bytes** (`app/services/file_validation.py`,
   signatures JPEG/PNG/PDF sur les octets de tête) — jamais l'extension du
   nom de fichier ni le `Content-Type` déclaré par le client, les deux se
   falsifiant trivialement (renommer un fichier quelconque en `.jpg`,
   mentir dans le header HTTP). Un selfie n'accepte que JPEG/PNG (jamais un
   PDF) ; les autres types de document tolèrent aussi un PDF (scan).
2. **Taille plafonnée** (`STORAGE_MAX_UPLOAD_BYTES`, défaut 8 Mo) — lu
   jusqu'à `max+1` octets côté endpoint pour détecter un dépassement sans
   bufferiser en mémoire un fichier arbitrairement gros.
3. **Clé de stockage aléatoire** (`uuid4().hex`), jamais le nom de fichier
   d'origine — non devinable, ne fuite aucune information. `verification.doc_url`
   stocke cette référence interne, jamais une URL publique.
4. **Rate limité par utilisateur authentifié** (fenêtre glissante, même
   mécanisme que `RATE_LIMIT_OTP_*`, `RATE_LIMIT_DOCUMENT_UPLOAD_PER_USER_*` ;
   compteurs partagés entre instances et persistants en staging/prod,
   table `rate_limit_hit`, voir `RATE_LIMIT_BACKEND`).
5. Crée/actualise la ligne `verification` (`status=pending`) et **recalcule
   immédiatement** `artisan_profile.verified_status`
   (`compute_verified_status`, §2.2) — c'est le seul endroit, avec le futur
   lot admin (Lot C), qui écrit cette colonne après le seed ; elle reste la
   source utilisée comme **filtre SQL** de visibilité par la recherche
   publique (§3.2), jamais comme valeur de sortie API (toujours recalculée
   à la volée par la couche de lecture).

**Stockage PUBLIC (photo de profil `POST /artisans/me/avatar`, photo de
couverture `POST /artisans/me/cover`)** — à ne
jamais confondre avec le stockage privé ci-dessus. Une photo de profil est
censée être visible (recherche, profil détaillé), contrairement à une CNI :
`get_avatar_storage_backend` (même `Protocol StorageBackend`, répertoire
dédié `AVATAR_STORAGE_LOCAL_DIR`, jamais `STORAGE_LOCAL_DIR`) écrit sous un
répertoire monté en **lecture publique** par `app.main`
(`StaticFiles`, `/static/avatars`). Mêmes garde-fous d'upload que les
documents (magic bytes JPEG/PNG uniquement, taille plafonnée
`AVATAR_MAX_UPLOAD_BYTES` / `COVER_MAX_UPLOAD_BYTES`), et un **rate limiting
par utilisateur** (`RATE_LIMIT_PROFILE_MEDIA_UPLOAD_PER_USER_*`, budget
unique partagé entre avatar et couverture, ajouté par le lot
`feat/profile-media` — avant lui, l'avatar n'en avait aucun). La couverture
partage le même stockage public que l'avatar (clé préfixée `cover-`) :
la distinction qui compte pour la confidentialité est public/privé, pas
avatar/couverture. `avatar_url`/`cover_url` renvoyés sont des **URL absolues**
(`{BACKEND_PUBLIC_BASE_URL}/static/avatars/...}`) et non relative : front
(Vercel) et back (Railway) sont deux services sur des origines différentes
en prod (§1), le front ne peut pas deviner l'origine du back.
`PATCH /artisans/me` continue par ailleurs d'accepter `avatar_url`/`cover_url`
en texte libre (coller une URL externe, **http(s) absolue uniquement** —
jamais `javascript:`/`data:`, ces URL étant rendues dans un `<img src>`
public) : les deux chemins écrivent le même champ, sans que l'un n'exclue
l'autre.

**Une photo envoyée n'est jamais servie telle quelle** (lot
`feat/media-hardening`, `app/services/image_processing.py`) : décodage
complet (un fichier à signature valide mais non décodable est refusé),
dimensions plafonnées AVANT décodage (`PROFILE_MEDIA_MAX_PIXELS`, anti-bombe
de décompression), orientation EXIF appliquée puis **toutes les métadonnées
retirées — dont la position GPS de la prise de vue**, redimensionnement
(`AVATAR_MAX_SIDE_PX` 512, `COVER_MAX_SIDE_PX` 1600, jamais d'agrandissement)
et recompression (JPEG q85, PNG si transparence). Le poids servi ne
dépendant plus du fichier envoyé, le plafond d'envoi passe à 10 Mo. Les
limites sont exposées par `GET /artisans/me/media-constraints` : le front
n'en recopie aucune. Les documents de vérification, eux, ne sont jamais
retouchés (preuve d'identité à examiner telle que déposée).

**Remplacement d'un média — deux règles de fiabilité**
(`app/services/profile_media.py`, communes aux deux médias) :

1. **On n'efface jamais un fichier qu'on ne peut pas prouver être le sien.**
   Comme l'URL reste éditable à la main, reconnaître le seul préfixe
   `/static/avatars/` permettait à un artisan de coller l'URL publique du
   média d'un autre artisan puis d'uploader une photo pour faire effacer le
   fichier de l'autre (défaut présent sur l'avatar avant le lot
   `feat/profile-media`, corrigé par lui). L'ancien fichier n'est supprimé
   que si sa clé a **exactement** le format généré
   (`{profile_id}/[cover-]{uuid hex}.{jpg|png}`), sous le répertoire du
   profil courant et du bon type de média.
2. **Suppression APRÈS le commit**, jamais avant : le service renvoie la
   clé obsolète, la route l'efface une fois la nouvelle URL durablement
   enregistrée. Un commit raté laisse au pire un fichier orphelin, jamais
   un profil qui pointe vers un fichier disparu. Best-effort, jamais
   bloquant.

---

## 3.4 Messagerie temps réel (lot `feat/messagerie`)

**Rattachement.** Une conversation par intervention, ouverte dans la même
transaction que l'intervention (`create_intervention`) : la discussion
existe dès la mise en relation, jamais avant — pas de canal libre vers un
artisan sans demande. Participants : exactement le client et l'artisan de
l'intervention ; l'admin est exclu (il n'a aucun besoin de lire les
échanges privés pour la vérification des artisans).

**REST = source de vérité.** Envoi, validation (vide refusé, 2 000
caractères max), masquage, persistance et curseurs de lecture passent
exclusivement par REST. Le WebSocket ne fait que **notifier**, après le
commit (`message.created`, `conversation.read`) ; une publication qui
échoue ne fait jamais échouer l'envoi. Conséquence : un message envoyé sans
WebSocket est enregistré exactement de la même façon — prouvé par les tests
`test_conversations_endpoint.py` (aucun WebSocket ouvert) et, côté front,
`ConversationScreen.test.tsx` (« envoie et confirme un message par REST
sans aucun temps réel », transport `unavailable`).

**Authentification du WebSocket — ticket à usage unique.** Un navigateur ne
peut pas poser d'en-tête `Authorization` sur un WebSocket, et un jeton dans
l'URL finit dans les journaux. Le front demande donc un ticket
(`POST /realtime/ticket`, authentifié par l'access token habituel) : JWT
`type="ws"`, 60 s, `jti` unique. Il le transmet comme **sous-protocole**
(`["teranga.v1", "ticket.<jwt>"]`) ; le serveur le vérifie **avant**
d'accepter (signature, type, expiration, compte non supprimé, rôle client
ou artisan, `jti` jamais consommé) et ne renvoie que `teranga.v1` — le
ticket n'est jamais réémis. Refus : fermeture `4401` avant acceptation (la
poignée de main échoue). Un access token classique est refusé comme ticket
(type différent) et inversement.

**Un canal par utilisateur** (`/realtime/ws`), pas par conversation : une
seule connexion par onglet alimente le fil ouvert et le badge de non-lus.
Isolation structurelle : le serveur ne publie un événement qu'aux sockets
des deux participants ; il n'existe aucun abonnement côté client, donc aucun
moyen de recevoir le fil d'autrui. Au plus 5 connexions par utilisateur
(`WS_MAX_CONNECTIONS_PER_USER`, la plus ancienne fermée en `4429`).
Heartbeat : ping serveur toutes les 25 s, fermeture `4408` sans signe du
client en 60 s ; le client répond `pong` et coupe lui-même une connexion
muette (70 s).

**Repli automatique WebSocket → polling (front).** `RealtimeConnection`
(`src/lib/realtime/`) expose un statut `connecting | open | unavailable`.
Tant qu'il n'est pas `open`, le fil ouvert relit `GET .../messages?since=`
toutes les 5 s et le badge relit `unread-count` toutes les 30 s ; dès qu'il
redevient `open`, le polling s'arrête. Reconnexion à backoff exponentiel
(1 s → 30 s, avec gigue), nouveau ticket à chaque tentative. À chaque
(re)connexion et à chaque retour au premier plan, le fil fait un rattrapage
`since` : un message publié pendant une coupure n'est jamais perdu. Onglet
en arrière-plan : connexion fermée et aucun polling (batterie, données).

**Masquage anti-fuite (second étage de l'anti-désintermédiation).**
`app/services/contact_masking.py`, appliqué au texte et aux légendes avant
stockage : numéros sénégalais à 9 chiffres (70/75/76/77/78/33 + 7 chiffres,
avec ou sans `+221`/`00221`/`221`, séparateurs espace . - / et
parenthèses), numéros internationaux (`+` ou `00`, 9 à 15 chiffres, dont
les liens `wa.me`) et e-mails → `[numéro masqué]` / `[e-mail masqué]`.
Seul le texte masqué est stocké (`contact_masked=true`), et les deux parties
voient l'avertissement : rien n'est caché à l'expéditeur. Pas de
sur-masquage : montants (`15 000 FCFA`), mesures (`2 robinets de 15 mm`),
heures, dates, quantités restent intacts (36 tests). **Limites assumées** :
un numéro épelé en toutes lettres, découpé sur plusieurs messages ou écrit
dans une photo n'est pas détecté — c'est le périmètre de la détection NLP
(Phase 3+, §8).

**Photos sans fuite.** `POST .../messages/image` : magic bytes JPEG/PNG uniquement,
10 Mo max, anti-bombe de décompression (50 Mpx), **réencodage serveur**
(EXIF et GPS retirés, 1 600 px max) — l'original n'est jamais conservé.
Stockage **privé** (`MESSAGE_ATTACHMENT_STORAGE_LOCAL_DIR`, clé aléatoire,
jamais servi en statique), lecture réservée aux deux participants
(`Cache-Control: private, no-store`). Le front le charge en blob
authentifié et révoque l'URL locale ensuite. Fichier supprimé si
l'enregistrement en base échoue. Rate limiting par utilisateur : 30
messages/min, 20 photos/10 min (`429 TROP_DE_DEMANDES`).

**Dette multi-instance — bus Redis pub/sub (à traiter AVANT de passer à
plusieurs instances backend).** `ConnectionManager` et le registre des
tickets consommés sont en mémoire, locaux au processus : exacts en instance
unique (cible de lancement, comme Railway 1 réplica). Avec plusieurs
instances : (1) un message enregistré par l'instance A n'est pas poussé aux
sockets ouvertes sur B — et comme un client dont le WebSocket est `open` ne
fait pas de polling, il ne le verrait qu'au prochain rattrapage
(reconnexion, retour au premier plan) : **dégradation silencieuse, pas
seulement un retard** ; (2) un ticket consommé sur A pourrait être rejoué
sur B pendant ses 60 s de validité. Correction prévue : publication via
Redis pub/sub (un canal par utilisateur, chaque instance relaie à ses
sockets) et consommation atomique du `jti` en Redis (`SET NX EX`). Le rate
limiting, lui, est déjà partagé (table `rate_limit_hit`, lot
`feat/media-hardening`).

## 3.5 Paiements : séquestre, espèces, commission, versement (lot `feat/paiements`)

**Principes (actés).**

- **Le montant vient TOUJOURS du serveur** : `intervention.agreed_amount_fcfa`,
  posé à l'acceptation du devis. `POST /payments/init` n'accepte aucun
  montant (un champ envoyé est ignoré ; testé).
- **Montants en ENTIERS de FCFA**, taux en points de base. Aucun float,
  nulle part (calcul, stockage, API, front).
- **Commission sur le taux FIGÉ** : `intervention.commission_rate_id`, résolu
  à la création de l'intervention (Lot 12a) — jamais le taux courant (test :
  le taux du métier passe à 25 % après la création, la commission reste à 10 %).
- **`platform_fee` découplée de `payment`** : une commission par
  intervention, créée `due` au premier paiement (ou à la complétion sans
  paiement), montant stocké une fois pour toutes.

**Règle d'arrondi de la commission.** `commission = (montant × taux_bps) //
10 000`, en entiers exacts : **troncature vers le bas (`floor`), en faveur de
l'artisan** — la commission ne dépasse jamais le taux annoncé, écart maximal
1 FCFA au détriment de Téranga. Exemple : 12 345 FCFA à 10 % = 1 234,5 →
**1 234**. Le net artisan est toujours `montant − commission` : leur somme
vaut le montant au franc près, par construction (vérifié par balayage sur
les trois règles). Réglage `COMMISSION_ROUNDING` (`floor` | `half_up` |
`ceil`), sans effet sur les commissions déjà enregistrées.
`app/services/commission_calculation.py`, testé en isolation.

**Enchaînement — paiement en ligne (séquestre).**

```
devis accepté (en_cours)
  └─ POST /payments/init {channel: wave|orange_money|carte}
       payment en_attente + checkout hébergé du fournisseur, commission « due »
  └─ webhook « checkout réussi » (signé, idempotent)
       payment RETENU (paid_at) — l'argent est chez Téranga
  └─ le client confirme la fin des travaux (POST /interventions/{id}/complete)
       même transaction : payment LIBERE, commission COLLECTEE,
                          payout EN_ATTENTE (net = montant − commission)
       après le commit : envoi du versement au fournisseur (clé payout-<id>)
                          -> payout ENVOYE (ou ECHOUE, relancé ensuite)
```

- **Qui déclenche quoi** : le client seul confirme la complétion (Lot 12b,
  aucun conflit d'intérêt) — c'est elle qui libère le séquestre. Un
  checkout encore ouvert bloque la complétion (`PAIEMENT_EN_COURS`).
- **Versement après le commit, dans sa propre transaction** : un
  fournisseur indisponible ne fait jamais échouer la confirmation du
  client ; le versement reste `echoue`, relancé par
  `scripts/dispatch_payouts.py` (sans double versement : clé
  d'idempotence). Destination : **toujours le numéro vérifié (OTP) du
  compte artisan**, copié sur le versement ; l'artisan choisit seulement le
  moyen (`PUT /payments/me/payout-settings`).
- **Double clic / changement d'avis** : une page encore ouverte pour le même
  moyen est réutilisée ; un autre moyen abandonne l'ancienne (`annule`).
  Si celle-ci est payée malgré tout, le webhook **rembourse aussitôt**
  (« paiement tardif ») : Téranga ne garde jamais d'argent sans cause.

**Espèces.** `POST /payments/init {channel: cash}` enregistre un paiement
`reussi` (réglé directement à l'artisan, sans séquestre ni versement) et la
commission reste **`due` par l'artisan** — mesure de la fuite. Le client
peut encore préférer le paiement en ligne tant que les travaux sont en
cours (jamais l'inverse une fois l'argent en séquestre). **Recouvrement de
la commission due : hors périmètre du code pour l'instant** (elle est
mesurée et affichée à l'artisan, pas encore recouvrée). Une complétion sans
aucun paiement enregistre aussi une commission `due` : le travail hors
plateforme est mesuré, jamais ignoré.

**Annulation, litige, remboursement.**

- Annulation (`POST /interventions/{id}/cancel`) : par l'**artisan** après
  avoir accepté (le client est alors remboursé), par le **client** tant
  qu'aucun fonds n'est en séquestre. Une fois payé en ligne, le client
  ouvre un litige : sinon il pourrait récupérer son argent après des
  travaux faits. Effets : fonds retenus -> **remboursés** (`rembourse`),
  checkout ouvert ou espèces -> `annule`, commission `annulee`, **jamais de
  versement ni de commission**, demande rouverte.
- Litige (`POST /interventions/{id}/dispute`, client ou artisan, travaux en
  cours) : l'argent est **gelé** tel quel. C'est aussi le recours de
  l'artisan si le client ne confirme jamais la fin. Un admin tranche
  (`POST /admin/disputes/{id}/resolve`) : `libere` -> même enchaînement
  qu'une complétion (versement du net) ; `rembourse` -> intervention
  annulée (arbitrage), client remboursé, aucune commission. Justification
  obligatoire, visible des deux parties.
- Remboursement **idempotent** (clé `refund-<id>`) et exécuté AVANT le
  commit : si notre transaction échoue après l'appel, la relance ne
  rembourse pas deux fois. Fournisseur indisponible -> 502, rien ne change.

**Webhook (robustesse production).** `POST /api/v1/webhooks/payments`,
public mais authentifié :

1. **Signature vérifiée avant toute lecture** — sandbox :
   `Teranga-Sandbox-Signature: t=<horodatage>,v1=<HMAC-SHA256(secret,
   "t.corps")>`, comparaison à temps constant, plusieurs `v1` acceptés
   (rotation du secret), horodatage hors fenêtre (5 min) refusé. Échec ->
   401, rien n'est écrit. Corps borné (64 Ko, 413), illisible -> 400.
2. **Idempotence par l'event id** : `INSERT ... ON CONFLICT DO NOTHING` sur
   `payment_event (provider, event_id)` — la base tranche, y compris entre
   deux livraisons simultanées. Un rejeu répond 200 `deja_traite` sans
   aucun effet. **Seconde défense** : la machine à états (un « succès » sur
   un paiement déjà retenu, libéré ou remboursé ne change rien). Preuve :
   tests de rejeu (×3, puis après la complétion : un seul versement) et
   **mutation** — retirer le contrôle d'event id OU affaiblir la machine à
   états fait échouer un test.
3. Paiement retrouvé par la référence du fournisseur, intervention
   **verrouillée** (`SELECT ... FOR UPDATE`, comme toute décision
   financière), puis : succès -> `retenu` ; échec -> `echoue` ; montant ou
   devise incohérents -> aucune transition, anomalie journalisée ;
   paiement ou type inconnu -> 200 ignoré (le fournisseur cesse ses
   tentatives), journalisé.

**Provider-agnostique — point de bascule sandbox -> réel.** Le métier
(`app/services/payments.py`) ne connaît que le contrat `PaymentProvider`
(`create_checkout`, `verify_webhook_signature`, `parse_event`, `refund`,
`send_payout`, types neutres). **Point de bascule unique** :
`app/services/payment_providers/__init__.py:build_payment_provider` +
`PAYMENT_PROVIDER`. Brancher un agrégateur réel (PayDunya, CinetPay, Wave
Business) = écrire son adaptateur (traduction de son API et de ses
webhooks), l'ajouter à ce point et à `Settings.payment_provider`,
renseigner `PAYMENT_WEBHOOK_SECRET` et ses identifiants, déclarer chez lui
l'URL du webhook — **sans toucher au code métier**. `sandbox` est interdit
en prod ; `disabled` coupe le paiement en ligne (espèces seules), la valeur
d'un déploiement sans agrégateur. Le sandbox reproduit le contrat : page
de paiement **hébergée par le backend** (hors du front, jeton signé et
expirant, CSP stricte), webhook signé et horodaté livré **par HTTP** au
backend (signature et idempotence exercées comme en production), event id
`EV_...`, montants en chaîne, références de remboursement/versement
déterministes. Option « livrer deux fois » sur la page : vérification
manuelle de l'idempotence.

**Accès aux montants.** Le résumé financier d'une intervention (total,
commission et taux, net, statuts datés, versement) n'est servi qu'à ses
deux parties et à l'admin ; un tiers reçoit 403 sans aucun montant (testé).
Côté front, la même donnée est présentée selon le rôle : le client voit
« Total à payer » et « aucun frais ajouté pour vous » (la commission est
nommée, prise sur la part de l'artisan) ; l'artisan voit prix, commission
(taux figé, « estimée » tant qu'elle n'est pas enregistrée) et « Vous
recevez ». Aucun montant n'est calculé par le front.

**Limites connues.** Recouvrement des commissions dues (cash) non codé ;
versements relancés par script (pas encore de planificateur) ; montant
incohérent signalé par un webhook traité manuellement ; litige sans
délai automatique de libération ; un seul fournisseur actif à la fois (un
remboursement exige le fournisseur d'origine).


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

### 4.3 Inscription vs connexion, choix du rôle (lot `feat/auth-signup`)

Jusqu'ici, `verify-otp` créait **toujours** un compte `client` par défaut si
le numéro était inconnu — aucune notion d'inscription vs connexion, aucun
choix de rôle. Ce lot rend l'intention explicite et verrouille deux
invariants de sécurité.

**Contrat** : `verify-otp` accepte `intent: "login" | "signup"` et
`role: "client" | "artisan"` (requis seulement en `signup`).
`request-otp` reste **inchangé** (toujours 204, non énumérant, aucun champ
supplémentaire).

**Pourquoi `request-otp` ne change pas.** Deux options étaient envisagées :
porter `intent` sur `request-otp`, ou dupliquer `verify-otp` en deux
endpoints. Aucune n'est nécessaire : `request-otp` ne fait rien de différent
selon l'intention (il génère et envoie un code, point) — le seul intérêt de
lui faire connaître l'intention serait de rejeter tôt un "compte déjà
existant" avant même la vérification du code, ce qui **réintroduirait une
énumération de comptes** non protégée par une preuve de possession du
numéro. La décision compte/rôle n'a de sens qu'au moment où l'état est
réellement muté (créer ou retrouver le `User`) : c'est `verify-otp`, jamais
avant. Dupliquer `verify-otp` en deux endpoints aurait par ailleurs
dupliqué toute la logique OTP sensible (hachage, tentatives, TTL,
consommation) pour une différence de quelques lignes de logique compte —
plus risqué que de la brancher sur un seul endpoint.

**Arbitrage énumération / clarté des messages.** `request-otp` reste
aveugle (204 systématique, identique que le compte existe ou non).
L'erreur qui révèle l'existence d'un compte (`COMPTE_DEJA_EXISTANT` en
signup, `COMPTE_INEXISTANT` en login) n'apparaît **qu'après** une
vérification de code OTP réussie, donc après une preuve de possession du
numéro (code livré uniquement par SMS, usage unique, TTL court, tentatives
limitées, haché PBKDF2). Un attaquant sans accès au SMS de la victime ne
peut donc jamais obtenir cette information ; seul le titulaire légitime du
numéro l'apprend sur son propre compte. Risque résiduel accepté : quelqu'un
qui contrôle déjà le SMS d'une victime (SIM-swap ciblé) apprend qu'un
compte existe — mais à ce stade il peut de toute façon prendre le compte
via l'OTP lui-même, l'information additionnelle n'ouvre donc pas de
nouvelle surface d'attaque.

**Rôle admin : aucun chemin via l'application.** `role` n'accepte que
`client`/`artisan` côté schéma (`Literal`), et `app.services.auth._SIGNUP_ROLES`
revalide explicitement cette allow-list côté service (défense en
profondeur, greppable et testée — `admin` ne devient jamais atteignable
même si le typage du schéma venait à être élargi par erreur). Aucun
endpoint, aucun paramètre de l'API n'attribue jamais `admin` : cette valeur
ne s'obtient que hors application (script/SQL direct), comme déjà annoncé
au §4.

**Un compte existant ne change jamais de rôle via ce flux.** En `login`,
le rôle de l'utilisateur retrouvé n'est jamais touché. En `signup`, un
numéro déjà existant est purement et simplement rejeté
(`COMPTE_DEJA_EXISTANT`, 409) — jamais de mise à jour de rôle sur un compte
existant, même via une nouvelle tentative d'inscription.

**Artisan_profile créé vide à l'inscription.** Un signup `role=artisan`
crée aussi la ligne `artisan_profile` associée : `is_available=false`
(explicite à la création, contrairement au défaut du modèle utilisé par le
seed/les tests) et `verified_status=none` (défaut du modèle, aucun document
soumis). L'onboarding (bio, métiers, zone d'intervention, documents de
vérification) reste un chantier distinct, hors périmètre de ce lot.

### 4.4 Rôle admin : bootstrap hors application (lot `feat/admin-verification`)

**Décision de sécurité actée, non négociable : le rôle `admin` ne s'obtient
JAMAIS via l'application.** Aucun endpoint, aucun paramètre d'API (schéma
d'entrée, query param, header) ne peut créer ni promouvoir un admin — ni au
signup (§4.3, `_SIGNUP_ROLES` verrouille explicitement `{client, artisan}`),
ni via aucune route de l'espace admin lui-même (`PATCH`/`POST
/admin/*` ne touchent jamais `role`, seulement `verification.status` et
`artisan_profile.verified_status` dérivé).

**Seul chemin : `scripts/create_admin.py`, en ligne de commande, côté
serveur.** Exige un accès direct à `DATABASE_URL` — jamais exposé sur le
réseau, jamais appelable depuis le frontend. Promeut un utilisateur
**déjà inscrit** via le parcours OTP normal (par son numéro E.164) ; ne
crée jamais de compte lui-même, refuse explicitement un numéro inconnu.
Idempotent : relancer sur un numéro déjà admin est un succès silencieux
(`already_admin=True`), pas une erreur — un opérateur qui rejoue la
commande par prudence ne casse rien. Usage exact et exemple dans
`backend/README.md`.

**Toutes les routes `/api/v1/admin/*` exigent `require_role(Role.ADMIN)`**
(même dépendance FastAPI que le reste de l'API, Lot 8) — un client ou un
artisan reçoit `403 ROLE_INSUFFISANT`, un anonyme `401`, exactement les
mêmes erreurs génériques que n'importe quelle autre route protégée par
rôle ailleurs dans l'API : aucun message, aucun code, aucun comportement
distinct ne permet à un tiers non autorisé de déduire qu'une route admin
existe spécifiquement. Côté frontend, `RequireAdminRoute` pousse le même
principe plus loin : un compte non-admin (y compris non authentifié) qui
atteint `/admin/*` voit l'écran "Page introuvable" — **exactement le même
composant qu'une route qui n'existe pas du tout**, jamais un message
"accès refusé" ni une redirection vers `/connexion`, l'un comme l'autre
confirmeraient l'existence de la section. Aucun lien vers `/admin/*`
n'apparaît nulle part dans la navigation (`BottomNav`, `Header`) pour un
compte non-admin — accès uniquement par URL directe, connue de l'admin.

**Traçabilité.** `reviewed_by`/`reviewed_at` (table `verification`, §2.2)
sont renseignés côté serveur à chaque décision (`app.services.admin_verification`)
depuis l'admin authentifié (JWT) — jamais un champ d'entrée accepté du
client, même en tentant de l'injecter dans le corps de la requête (testé).
Un document déjà tranché ne se re-tranche pas (`VERIFICATION_DEJA_TRAITEE`,
409) : chaque ligne `verification` ne porte donc jamais plus d'une
décision, `reviewed_by`/`reviewed_at` restent un audit trail fiable et
non réécrit pour ce lot. **Recommandation, non construite ici** : une table
d'audit dédiée (journal append-only de toutes les actions admin, au-delà
de la seule dernière décision par document) serait utile si l'espace admin
grandit (plusieurs admins, besoin d'historique complet même après un
éventuel changement de décision) — hors périmètre pour l'instant, `reviewed_by`/
`reviewed_at` suffisent au besoin actuel (une décision définitive par
document).

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
    vide ; depuis le lot `feat/paiements` : chiffre d'affaires encaissé,
    séquestre libéré ou espèces réglées, avant commission, §3.5),
    `interventions_count` (interventions `terminee`), `rating_avg`/
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
- **Lot `feat/auth-signup` — Inscription vs connexion, choix du rôle.**
  `verify-otp` porte désormais `intent`/`role` explicites (§4.3) : fin de
  l'auto-signup implicite en `client`, `admin` verrouillé serveur (allow-list
  explicite en plus du typage), un compte existant ne change jamais de rôle.
  Un signup `role=artisan` crée aussi son `artisan_profile` vide
  (`is_available=false`, `verified_status=none`). Front : nouveau point
  d'entrée `/connexion` (choix Se connecter/Créer un compte,
  `AuthEntryScreen`), `/connexion/role` (choix client/artisan,
  `RoleSelectScreen`, la carte artisan reprend déjà l'identité `bg-primary`
  de l'Espace Pro), `PhoneScreen`/`OtpScreen` déplacés/adaptés pour relayer
  `intent`/`role`, écran de bienvenue dédié `/bienvenue-artisan` après une
  inscription artisan. *But : un vrai parcours d'inscription, sans ouvrir
  de chemin vers le rôle admin.*
- **Lot `feat/artisan-onboarding` — Profil, métiers, documents de
  vérification.** Un artisan créé vide (Lot `feat/auth-signup`) complète son
  profil et dépose ses documents, sans être éligible à une mise en relation
  tant qu'il n'est pas vérifié. Couche de stockage privée abstraite
  (`StorageBackend`, §3.3), `PATCH /artisans/me` étendu (bio, expérience,
  localisation, avatar — mise à jour partielle), `POST`/`DELETE
  /artisans/me/trades` (métiers exercés), `POST`/`GET
  /artisans/me/documents` + `GET .../content` (upload sécurisé : magic
  bytes, taille plafonnée, référence non devinable, rate limité — détail
  §3.3). Chaque document déposé recalcule immédiatement `verified_status`
  (`NONE -> PENDING` dès le premier document). Deux garde-fous
  d'éligibilité : `POST /interventions` rejette déjà un artisan non vérifié
  (`ARTISAN_NON_VERIFIE`, en place depuis le Lot 12) et `GET /artisans`
  (recherche publique) l'exclut désormais entièrement — décision actée
  (invisible plutôt que visible avec mention, §3.2) — tandis que `GET
  /artisans/{id}` reste accessible à l'artisan pour son propre onboarding.
  Front : parcours `/bienvenue-artisan` → onboarding (profil, métiers,
  documents, checklist de progression), bandeau de statut "en cours de
  vérification" tant que non vérifié, `/pro` affiche l'état d'onboarding au
  lieu d'un dashboard vide pour un artisan non encore vérifié. *But : un
  artisan peut se préparer à être vérifié, sans jamais pouvoir contourner la
  vérification pour être contacté.*
- **Lot `feat/admin-verification` — Espace admin de revue.** Ferme la boucle
  ouverte par l'onboarding artisan : les documents déposés (Lot B) restaient
  `pending` indéfiniment, personne ne pouvait les approuver/rejeter. Rôle
  admin bootstrapé exclusivement par script (`scripts/create_admin.py`,
  jamais un endpoint — §4.4). `GET /admin/verifications` (file d'attente
  FIFO, filtrable par statut), `GET .../{id}/content` (binaire via la même
  couche de stockage privée que Lot B), `POST .../{id}/approve` et
  `.../reject` (`note` obligatoire, `reviewed_by`/`reviewed_at` serveur,
  jamais falsifiables), `GET /admin/artisans/{id}` (vue admin, tous les
  documents). Chaque décision recalcule immédiatement
  `artisan_profile.verified_status` (`compute_verified_status`, §2.2) : une
  approbation complète rend l'artisan visible en recherche (§3.2) et
  contactable (`POST /interventions` ne rejette plus `ARTISAN_NON_VERIFIE`),
  un rejet le laisse invisible et non contactable, avec motif visible côté
  artisan (Lot B) qui peut renvoyer un document (testé de bout en bout,
  `pending -> rejected -> pending` après renvoi). Toutes les routes
  `/admin/*` verrouillées par `require_role(Role.ADMIN)`, indiscernables
  d'une route protégée par rôle ordinaire pour un tiers non autorisé.
  Front : `/admin/verifications` (hors `MainLayout`, outil interne),
  `RequireAdminRoute` affiche l'écran 404 standard pour tout compte non-admin
  (jamais un message "accès refusé", jamais de lien visible dans la
  navigation). *But : le cycle de vérification artisan est enfin complet,
  de l'upload à la décision humaine.*
- **Lot `fix/user-name-and-contact-privacy` — Nom réel à l'inscription,
  confidentialité du contact.** Corrige la racine d'un défaut constaté sur la
  fiche artisan : le numéro de téléphone s'affichait à la place du nom, car
  `full_name` était rempli avec le téléphone en guise de placeholder à
  l'inscription (aucun nom collecté avant ce lot — `resolve_account_for_intent`,
  `app/services/auth.py`). `full_name` est désormais **requis** au signup pour
  les deux rôles (`app/core/full_name.py`, bornes 2–150 caractères, seule
  source de vérité partagée signup/édition), le placeholder est supprimé.
  Édition après coup : `PATCH /users/me` (nouveau, rôle-agnostique — client
  et artisan) et `full_name` accepté dans `PATCH /artisans/me` (pour que
  l'artisan n'ait qu'un seul endpoint à connaître). Défense en profondeur :
  `app/services/identity.py::public_display_name` masque tout `full_name`
  qui ressemble encore à un numéro de téléphone (`looks_like_phone_number`,
  `app/core/phone.py`) derrière un repli neutre partagé ("Membre Téranga"),
  appliqué à chaque point de sérialisation publique (`GET /artisans`,
  `/artisans/{id}`, `/artisans/{id}/reviews`, l'avis embarqué dans
  `InterventionOut`) — jamais en vue de soi (`/auth/me`) ni côté admin, qui
  doivent voir la valeur réelle. Verrouillé par un test dédié
  (`test_public_contact_privacy.py`) : aucun numéro de téléphone n'apparaît
  jamais dans une réponse publique sérialisée, même via un compte hérité
  simulé avec `full_name = phone`. `scripts/seed.py` construisait déjà ses
  `User` directement (hors `resolve_account_for_intent`) donc avait déjà de
  vrais noms — vérifié, aucun changement nécessaire. Front : nouvel écran
  `/connexion/nom` (`NameScreen`) entre le choix du rôle et le téléphone,
  seulement en signup ; édition du nom ajoutée à l'onboarding artisan (Mon
  profil) et au profil client (icône crayon inline). *But : plus aucun
  compte ne peut se créer sans nom, et le nom affiché publiquement n'est
  jamais un numéro de téléphone.*
- **Lot `feat/profile-media` — Photo de couverture, fiabilité des médias
  publics.** Nouvel endpoint `POST /artisans/me/cover` (même régime PUBLIC
  que l'avatar : magic bytes JPEG/PNG, `COVER_MAX_UPLOAD_BYTES`, stockage
  `get_avatar_storage_backend`, URL absolue), `cover_url` accepté dans
  `PATCH /artisans/me`. Rate limiting par utilisateur ajouté sur les deux
  uploads, **budget partagé** (`RATE_LIMIT_PROFILE_MEDIA_UPLOAD_PER_USER_*`,
  20 envois / 10 min, `429 TROP_DE_DEMANDES`) — l'avatar n'en avait aucun.
  Durcissement commun avatar/couverture (`app/services/profile_media.py`,
  §3.3) : suppression de l'ancien fichier limitée à une clé prouvée
  appartenir au profil et au type de média (corrige une suppression
  possible du média d'un autre artisan via une URL collée à la main),
  déplacée **après** le commit ; `avatar_url`/`cover_url` saisies à la main
  restreintes au http(s) absolu. Tests : `test_artisan_cover_endpoint.py`,
  `test_profile_media_privacy.py`, `test_profile_media_rate_limit.py`,
  `test_profile_media_ownership.py`. Front : bandeau de couverture dans
  l'onboarding (aperçu fidèle à la fiche publique, avatar en
  chevauchement), un bouton, un état d'envoi et un message d'erreur par
  photo, pré-contrôle local type/taille (aucune requête ni budget consommé
  pour un fichier voué au refus), champ URL de couverture à côté de celui
  de l'avatar. *But : l'artisan maîtrise toute l'image de sa fiche
  publique, sans qu'un autre compte puisse jamais y toucher.*
- **Lot `feat/media-hardening` — Médias publics et rate limiting fiables.**
  Clôt les trois dettes laissées par `feat/profile-media`. (1) **Rate
  limiting partagé** : table `rate_limit_hit` + `PostgresRateLimiter`
  (OTP, triage IA, documents, photos) — compteurs communs à toutes les
  instances et conservés au redémarrage, transaction propre à chaque
  vérification, verrou consultatif par clé contre les requêtes simultanées,
  clés stockées en empreinte SHA-256 ; `RATE_LIMIT_BACKEND` : `memory` en
  dev, `postgres` sinon, `memory` refusé hors dev. (2) **Réencodage
  serveur** des photos (Pillow, §3.3) : EXIF/GPS retirés, redimensionnement,
  recompression, anti-bombe de décompression. (3) **Source unique des
  limites** : `GET /artisans/me/media-constraints`, lu par l'onboarding
  (pré-contrôle, `accept`, texte d'aide) — plus aucun plafond en dur côté
  front. *But : ce que la fiche publique affiche ne révèle rien de plus que
  la photo, et les limites anti-abus tiennent en production réelle.*
- **Lot 13 — Retrait d'Express.** ✅ (branche `chore/remove-express`) Proxy
  `/api/v1` d'abord recréé dans Vite (`vite.config.ts`, `BACKEND_URL` validée
  au démarrage, port 3000 strict) et testé seul, Express encore présent ;
  puis `server.ts` supprimé avec `express`, `http-proxy-middleware`,
  `@google/genai`, `dotenv`, `tsx`, `esbuild` (preuve grep : importés par
  `server.ts` seul). Scripts `dev = vite`, `build = vite build` (statique
  seul), `preview`. Production : §1 « Service du front ». Dette IA close :
  l'endpoint Gemini `/api/analyze-problem`, `GEMINI_API_KEY`, `APP_URL` et
  `metadata.json` (AI Studio) supprimés — le triage FastAPI est la seule
  implémentation. Fallback mock silencieux supprimé : `api = httpApiClient`,
  qui implémente tout `ApiClient` (compilation), quatre méthodes servies par
  le seul mock et jamais appelées retirées du contrat (preuve grep),
  `notImplemented()` / code `not_implemented` pour toute fonctionnalité
  future sans backend, mock réservé aux tests (règle ESLint). Au passage :
  `npm audit` 16 → 0 (dont react-router 7.18.4, seule dépendance concernée
  embarquée dans le bundle). Parcours vérifié bout en bout via le proxy
  Vite (recherche, OTP, triage IA, uploads, dashboard, refresh/logout).
  *But : un seul backend.*
- **Lot `feat/messagerie` — Messagerie in-app temps réel.** Une
  conversation par intervention (créée avec elle, migration `c0a26cec109e`
  qui ouvre aussi celle des interventions existantes), deux participants,
  admin exclu, non-participant = même 403 qu'un fil inexistant. REST source
  de vérité (liste paginée par activité, historique `since`/`before`, envoi
  texte et photo, curseurs de lecture, compteur de non-lus) ; WebSocket de
  notification par utilisateur, authentifié par ticket à usage unique en
  sous-protocole, heartbeat ; repli automatique sur polling côté front.
  Masquage des numéros sénégalais/internationaux et des e-mails avant
  stockage, avertissement visible des deux parties. Photos réencodées
  (EXIF/GPS retirés), stockage privé, servies aux seuls participants.
  Front : `/messages`, `/messages/:id`, badge de non-lus temps réel dans les
  deux navigations, accès au fil depuis la fiche artisan et la carte
  d'intervention ; `ComingSoon` supprimé. Détail §3.4, dette Redis
  multi-instance comprise. *But : client et artisan se parlent sur la
  plateforme, sans s'échanger leurs numéros.*
- **Lot 14 — `feat/paiements` — Moteur de paiement.** ✅ Séquestre en ligne
  (payé à l'acceptation du devis, `retenu`, libéré à la complétion confirmée
  par le client, net versé vers le numéro vérifié de l'artisan), espèces
  enregistrées (commission `due`), commission calculée en entiers sur le
  taux FIGÉ (arrondi `floor` en faveur de l'artisan), annulation
  (remboursement idempotent), litige qui gèle l'argent et arbitrage admin.
  Provider-agnostique (`PaymentProvider`), fournisseur sandbox reproduisant
  le contrat d'un agrégateur (checkout hébergé, webhook HMAC horodaté,
  event id) ; webhook idempotent (`payment_event`), prouvé par mutation.
  Front : écran de paiement, volet financier par rôle dans le suivi, gains
  et versements Pro, historique client, litiges admin. Détail §3.5.
  *But : le client paie en confiance, l'artisan sait exactement ce qu'il
  touche, Téranga mesure tout — y compris le cash.*
- **Lot 15 — Déploiement Railway** (2 services + Postgres managé, bascule
  `DATABASE_URL`) + branchement d'un agrégateur réel (§3.5, point de
  bascule). *À séquencer selon priorités.*

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
- **Mise en œuvre (lot `feat/paiements`, §3.5)** : séquestre en ligne (le
  client est protégé, l'artisan payé dès la confirmation), commission
  prélevée sur la part de l'artisan — **aucun frais ajouté au client**, dit
  en clair à l'écran ; en cash ou sans paiement, la commission est
  enregistrée `due` (mesure de la fuite ; recouvrement hors périmètre code).

---

## 8. Ce qui reste hors périmètre Phase 2 (noté pour plus tard)

Scoring de fiabilité des artisans, détection de fuite par NLP sur la messagerie,
assistant conversationnel, i18n Wolof/Français, tarification dynamique,
notifications push. Phase 3+.

Paiements (après le lot `feat/paiements`, §3.5) : recouvrement des
commissions dues sur le cash, planification des relances de versements,
libération automatique d'un séquestre après un délai sans contestation,
abonnement « Vérifié » (la `platform_fee` découplée le permet déjà).
