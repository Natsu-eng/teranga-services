# DEPLOYMENT — Mise en production de Téranga Services

Runbook de mise en ligne sur **Railway** : frontend statique, backend
FastAPI, PostgreSQL + PostGIS managé, Redis, stockage objet S3-compatible
(Cloudflare R2 recommandé). Lancement prévu **en espèces seulement** (paiement
en ligne branché plus tard, par simple configuration).

Tout ce qui suit a été exercé en développement avec des replis : sans Redis,
sans S3 et avec le paiement sandbox, le dev tourne exactement comme avant.
Les commandes de la CLI Railway (`railway ssh`…) et la construction des
images Docker n'ont pas pu être exécutées lors de la préparation (aucun
compte Railway, Docker arrêté) : à valider avec `railway --help` et un
premier `docker build` avant le jour J.

**Autre chemin, pour la beta de test** : Render (backend) + Supabase
(PostgreSQL/PostGIS et stockage) + Vercel (front), décrit au **§12**. Il ne
modifie rien au chemin Railway ci-dessous.

---

## 0. À lire avant tout : bloquants et risques

| # | Sujet | Statut | Conséquence |
|---|---|---|---|
| 1 | **Fournisseur SMS réel** | **BLOQUANT** | Aucun fournisseur commercial n'est implémenté (`SMS_PROVIDER` : `console` ou `unconfigured`). En production, les deux sont **refusés au démarrage** : sans SMS, personne ne recevrait son code de connexion. Il faut choisir un fournisseur (Orange SMS API, Twilio…) et écrire son adaptateur dans `backend/app/services/sms.py` (contrat `SmsProvider`, une méthode `send_otp`). C'est le seul point qui empêche aujourd'hui la configuration de production de démarrer (testé : `test_complete_production_config_is_blocked_only_by_the_missing_sms_provider`). |
| 2 | **PostGIS sur Railway** | **VÉRIFICATION OBLIGATOIRE** | Le Postgres standard de Railway ne garantit pas l'extension PostGIS. La première migration (`CREATE EXTENSION postgis`) doit réussir, sinon aucun déploiement ne passe. Voir §4.1. |
| 3 | **Disque éphémère** | **Garde-fou en place** | Le disque d'un service Railway est **effacé à chaque déploiement**. Tout fichier stocké localement (CNI, selfies, photos) serait **perdu**. `STORAGE_BACKEND=local` est donc **refusé** en production : stockage S3/R2 obligatoire. Voir §4.3. |
| 4 | **Clé Mistral** | À renouveler | Générer une **nouvelle** clé dédiée à la production (jamais celle du dev), voir §8. Facultatif : sans clé, le triage IA reste sur l'heuristique. |

---

## 1. Topologie

```
Navigateur ──HTTPS──▶ Frontend (statique : Vercel, ou Railway + Caddy)
     │
     └──HTTPS / WSS──▶ Backend FastAPI (Railway, image Docker)
                          ├── PostgreSQL 16 + PostGIS (Railway, volume persistant)
                          ├── Redis (Railway) — rate limiting, temps réel, tickets WebSocket
                          └── Stockage S3 (Cloudflare R2) — bucket PRIVÉ + bucket PUBLIC
```

- Front et backend sont sur **deux origines** (ex. `https://teranga.sn` et
  `https://api.teranga.sn`) : le front est construit avec l'URL absolue de
  l'API (`VITE_API_BASE_URL`), l'origine du front est déclarée dans
  `CORS_ORIGINS`.
- Les jetons passent par l'en-tête `Authorization` (aucun cookie) ; la
  messagerie temps réel par WebSocket `wss://…/api/v1/realtime/ws`, avec repli
  automatique en relecture REST.

---

## 2. Prérequis

**Comptes**

- Railway (projet avec 4 services : backend, frontend, PostgreSQL+PostGIS, Redis).
- Cloudflare (R2) ou AWS (S3) pour les fichiers.
- Un nom de domaine (DNS) pour le front et l'API.
- Un fournisseur SMS (bloquant n°1).
- Facultatif : Mistral (triage IA), Vercel (si le front y est hébergé).
- Plus tard : un agrégateur de paiement (PayDunya, CinetPay, Wave Business…).

**Secrets à générer** (une valeur par environnement, jamais réutilisée, jamais
commitée) :

```bash
# JWT_SECRET (48 octets aléatoires)
python -c "import secrets; print(secrets.token_urlsafe(48))"
# PAYMENT_WEBHOOK_SECRET (le jour où un agrégateur est branché ; il le fournit en général)
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 3. Variables d'environnement

Source de vérité : `backend/.env.example` (chaque réglage y est commenté ; un
test garantit qu'aucun n'y manque) et `frontend/.env.example`.

### 3.1 Backend — obligatoires en production

Le démarrage en production **échoue** (liste complète des problèmes d'un
coup) si l'une manque, garde une valeur d'exemple, ou pointe vers du local.

| Variable | Rôle | Valeur en production |
|---|---|---|
| `ENVIRONMENT` | Ensemble fermé : `development`, `test`, `staging`, `production` | `production` |
| `DATABASE_URL` | Base PostgreSQL+PostGIS, driver asyncpg | `postgresql+asyncpg://…` (mot de passe réel, hôte non local) |
| `JWT_SECRET` | Signature des jetons (≥ 32 caractères) | secret aléatoire (§2) |
| `SMS_PROVIDER` | Envoi des codes OTP | fournisseur réel (**bloquant n°1**) |
| `FRONTEND_PUBLIC_BASE_URL` | URL publique du front (retours de paiement) | `https://teranga.sn` |
| `BACKEND_PUBLIC_BASE_URL` | URL publique de l'API | `https://api.teranga.sn` |
| `CORS_ORIGINS` | Origines autorisées, sans joker ni `/` final | `https://teranga.sn` (doit contenir l'origine du front) |
| `TRUSTED_PROXY_HOPS` | Proxys de confiance (IP réelle du client pour le rate limiting) | `1` (proxy Railway) |
| `STORAGE_BACKEND` | Stockage des fichiers | `s3` |
| `S3_ENDPOINT_URL` | Point d'accès S3 | R2 : `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` ; AWS : vide |
| `S3_REGION` | Région | R2 : `auto` ; AWS : région du bucket |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | Clé d'API du stockage | jeton R2 lecture/écriture sur les 2 buckets |
| `S3_PRIVATE_BUCKET` | Documents d'identité, photos de la messagerie | ex. `teranga-prive` (aucun accès public) |
| `S3_PUBLIC_BUCKET` | Photos de profil et de couverture | ex. `teranga-public` (≠ du privé, refusé sinon) |
| `S3_PUBLIC_BASE_URL` | URL publique HTTPS du bucket public | ex. `https://media.teranga.sn` |
| `PAYMENT_PROVIDER` | Paiement en ligne | `disabled` au lancement (`sandbox` refusé) |

### 3.2 Backend — selon les options

| Variable | Rôle | Quand |
|---|---|---|
| `REDIS_URL` | Redis partagé (`redis://` / `rediss://`) : rate limiting, diffusion temps réel, tickets WebSocket | **Fortement recommandée** ; **obligatoire dès 2 instances** (ou `WEB_CONCURRENCY` > 1). Sans elle : rate limiting en PostgreSQL, temps réel limité à une instance. |
| `RATE_LIMIT_BACKEND` | Stockage des compteurs | Laisser **vide** : `redis` si `REDIS_URL`, sinon `postgres` (`memory` refusé) |
| `PAYMENT_WEBHOOK_SECRET` | Signature des webhooks de paiement (≥ 32) | Obligatoire dès qu'un agrégateur est branché |
| `PAYMENT_ONLINE_CHANNELS`, `PAYMENT_CASH_ENABLED` | Moyens proposés | Défauts adaptés ; espèces activées |
| `AI_TRIAGE_PROVIDER`, `MISTRAL_API_KEY` | Triage IA | `heuristic` (défaut, sans clé) ou `mistral` + clé (refusé sans clé) |
| `AVATAR_STORAGE_BACKEND`, `MESSAGE_ATTACHMENT_STORAGE_BACKEND` | Variantes par usage | Laisser **vides** (héritent de `STORAGE_BACKEND`) |
| `LOG_LEVEL` | Niveau de journalisation | `INFO` (logs JSON hors development/test) |
| `WEB_CONCURRENCY` | Workers uvicorn par conteneur (lu par uvicorn) | `1` par défaut ; > 1 exige `REDIS_URL` |
| `PORT` | Port d'écoute | Fourni par Railway, ne pas définir |

### 3.3 Backend — réglages avec défaut sûr

À ne modifier qu'en connaissance de cause (détail dans `backend/.env.example`) :
OTP (`OTP_*` ; `OTP_TEST_*` : staging uniquement, §10 ; `RATE_LIMIT_OTP_*`), JWT (`JWT_ACCESS_TTL_SECONDS`,
`JWT_REFRESH_TTL_SECONDS`), téléphone (`PHONE_DEFAULT_REGION`,
`PHONE_ALLOWED_REGIONS`), recherche et pagination (`ARTISAN_SEARCH_*`,
`PAGINATION_*`), vérification (`VERIFICATION_REQUIRED_DOC_TYPES`), Mistral
(`MISTRAL_MODEL`, `MISTRAL_API_BASE_URL`, `MISTRAL_TIMEOUT_SECONDS`), envois
et médias (`STORAGE_MAX_UPLOAD_BYTES`, `AVATAR_*`, `COVER_*`,
`PROFILE_MEDIA_MAX_PIXELS`, `MESSAGE_ATTACHMENT_*`, `RATE_LIMIT_*`),
messagerie (`MESSAGING_*`, `WS_*`), demandes (`REQUEST_OPEN_TTL_DAYS`),
commission (`COMMISSION_ROUNDING`, `COMMISSION_RATE_MAX_BPS`), paiement
(`PAYMENT_WEBHOOK_TOLERANCE_SECONDS`, `PAYMENT_WEBHOOK_MAX_BODY_BYTES`,
`PAYMENT_CHECKOUT_TTL_SECONDS`, `PAYMENT_CURRENCY`,
`PAYMENT_PROVIDER_TIMEOUT_SECONDS`, `PAYOUT_*`). Sans objet en production :
`*_LOCAL_DIR` (stockage local), `SANDBOX_WEBHOOK_URL` (sandbox).

### 3.4 Frontend

| Variable | Rôle | Valeur |
|---|---|---|
| `VITE_API_BASE_URL` | URL de l'API vue par le navigateur, **figée au build** (publique, jamais un secret) | `https://api.teranga.sn/api/v1` |
| `BACKEND_URL` | Proxy de dev de Vite uniquement | Sans objet en production |

Changer `VITE_API_BASE_URL` impose de **reconstruire** le front.

---

## 4. Mise en ligne pas à pas

### 4.1 PostgreSQL + PostGIS (vérification obligatoire)

1. Dans Railway, créer la base à partir d'un **modèle PostGIS** (image
   `postgis/postgis`, PostgreSQL 16 + PostGIS 3) **avec un volume
   persistant**, plutôt que le Postgres standard. À défaut, un service Docker
   `postgis/postgis:16-3.4` avec volume monté sur `/var/lib/postgresql/data`.
2. Vérifier l'extension **avant** le premier déploiement du backend :
   ```sql
   SELECT name, default_version, installed_version
   FROM pg_available_extensions WHERE name = 'postgis';
   ```
   La ligne doit exister. La migration `ef1968cb5881` exécute
   `CREATE EXTENSION IF NOT EXISTS postgis` ; l'utilisateur de la base doit en
   avoir le droit (propriétaire de la base, cas du modèle Railway).
3. Après les migrations (§4.4) : `SELECT postgis_full_version();` doit
   répondre. **Go-live interdit tant que ce n'est pas le cas** : toute la
   recherche par proximité et les zones d'intervention en dépendent.
4. Activer les sauvegardes de la base (Railway : backups du volume) et
   tester une restauration avant le lancement.

### 4.2 Redis

Créer un service **Redis** Railway. Dans le backend :
`REDIS_URL=${{Redis.REDIS_URL}}` (variable de référence Railway).

### 4.3 Stockage S3 / R2 (obligatoire)

1. Créer **deux buckets** : `teranga-prive` et `teranga-public`.
2. `teranga-prive` : **aucun accès public** (ni domaine public, ni URL
   r2.dev). Les documents d'identité n'en sortent que par les endpoints
   authentifiés du backend.
3. `teranga-public` : rattacher un **domaine personnalisé** (ex.
   `media.teranga.sn`) → `S3_PUBLIC_BASE_URL=https://media.teranga.sn`.
4. Créer un **jeton d'API R2** limité à ces deux buckets (lecture/écriture)
   → `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.
5. Garanties du code : deux buckets différents exigés au démarrage, jamais
   d'ACL publique posée objet par objet, contenus privés en
   `Cache-Control: private, no-store`.

### 4.4 Backend

1. Service Railway depuis le dépôt, **Root Directory = `backend`**. Railway
   lit `backend/railway.json` : build par `backend/Dockerfile`, puis
   - **pré-déploiement** : `alembic upgrade head` (migrations) ;
   - **healthcheck** : `/api/v1/health/ready` (le nouveau déploiement ne
     reçoit du trafic que lorsque la base répond).
2. Renseigner les variables du §3.1 (et §3.2). Toute erreur de configuration
   fait échouer le démarrage avec la liste des problèmes (visible dans les
   journaux du déploiement).
3. Domaine : `api.teranga.sn` (Railway fournit le certificat TLS).

### 4.5 Frontend

**Option A — Vercel** (recommandée, configuration déjà complète) : Root
Directory = `frontend`, variable `VITE_API_BASE_URL`. `vercel.json` porte le
fallback SPA, le cache des assets et les en-têtes de sécurité ; Vercel ajoute
HSTS.

**Option B — Railway** : service Root Directory = `frontend` ; Railway lit
`frontend/railway.json` (build par `frontend/Dockerfile` : build Vite puis
Caddy). Déclarer `VITE_API_BASE_URL` dans les variables du service (transmise
au build). Le `Caddyfile` sert les **mêmes en-têtes** que `vercel.json` (test
de parité) + HSTS.

Domaine : `teranga.sn`. Puis vérifier que `CORS_ORIGINS` du backend contient
exactement `https://teranga.sn`.

### 4.6 Données de référence

Une seule fois (idempotent, sûr à relancer), **dans le conteneur du
backend**, qui seul joint la base par le réseau privé de Railway :

```bash
railway ssh --service backend          # shell dans le conteneur déployé
python scripts/seed_reference.py       # lancement sans commission : --rate-bps 0
```

Attention : `railway run` exécute la commande sur VOTRE poste, avec les
variables du service, mais l'adresse privée de la base
(`*.railway.internal`) n'y est pas joignable. Pour une exécution locale, il
faut remplacer `DATABASE_URL` par l'URL publique (proxy TCP) de la base.

Crée les métiers et le taux de commission global initial (journalisé).
**Ne jamais lancer `scripts/seed.py`** en production (données de
démonstration) : il refuse de toute façon de s'y exécuter.

### 4.7 Premier administrateur

1. La personne crée son compte normalement sur le site (téléphone + code
   SMS — d'où le bloquant n°1).
2. Puis, dans le conteneur du backend (voir §4.6) :
   ```bash
   railway ssh --service backend
   python scripts/create_admin.py +221XXXXXXXXX
   ```
   (confirmation interactive ; journalisé `admin.bootstrap`). Les admins
   suivants se gèrent depuis le back-office (`/admin/utilisateurs`).

### 4.8 Tâche planifiée

Créer un service **cron** Railway (même image que le backend, mêmes
variables) qui exécute une fois par jour :
`python scripts/expire_requests.py` (enregistre l'expiration des demandes ;
la règle s'applique déjà sans lui). `scripts/dispatch_payouts.py` ne sert
qu'avec le paiement en ligne.

### 4.9 Test de fumée (après chaque mise en ligne)

- [ ] `GET https://api.teranga.sn/api/v1/health` → 200 ; `/health/ready` → 200.
- [ ] En-têtes de l'API : `Strict-Transport-Security`, `Content-Security-Policy`,
      `X-Frame-Options: DENY` présents ; `/docs` → 404 (désactivé en production).
- [ ] Le site s'ouvre, une page profonde rechargée (`/artisans/…`) s'affiche (fallback SPA).
- [ ] Inscription : le code SMS arrive ; connexion OK.
- [ ] Recherche d'artisans à proximité (PostGIS) OK.
- [ ] Un artisan envoie sa CNI : l'objet n'existe que dans le bucket privé ;
      l'admin la voit dans `/admin/verifications`.
- [ ] Une photo de profil s'affiche depuis `S3_PUBLIC_BASE_URL`.
- [ ] Messagerie : un message arrive en temps réel chez l'autre partie.
- [ ] Paiement : seule l'option espèces est proposée, aucune mention de séquestre.
- [ ] Le back-office s'ouvre pour l'admin ; « Page introuvable » pour un client.
- [ ] Aucun bandeau « Version de test » (`GET /api/v1/meta` → `"environment": "production"`, `"otp_test_mode": false`).
- [ ] `https://teranga.sn/manifest.webmanifest` et `/sw.js` → 200, `Cache-Control: no-cache` ;
      Chrome Android propose « Installer l'application » (§11).

---

## 5. Stratégie de migration

- Les migrations s'exécutent **avant** la mise en service de la nouvelle
  version (`preDeployCommand`). Si elles échouent, le déploiement est
  **annulé** : l'ancienne version continue de servir.
- Pendant la migration, l'**ancienne** version tourne encore : chaque
  migration doit rester compatible avec le code précédent (ajouter avant
  d'utiliser, supprimer en deux temps : d'abord le code, puis la colonne au
  déploiement suivant).
- Retour arrière : redéployer la version précédente ; ne lancer
  `alembic downgrade` qu'après avoir vérifié que la migration est réversible
  sans perte (toutes les migrations du dépôt ont un `downgrade`, mais une
  suppression de données ne se rattrape pas) et après sauvegarde.
- Le journal d'audit est en ajout seul **au niveau de la base** : aucune
  migration ne doit le modifier ni le vider.

## 6. Healthchecks

| Endpoint | Rôle | Usage |
|---|---|---|
| `/api/v1/health` | Vivacité (le processus répond), sans dépendance | Supervision externe (UptimeRobot, Better Stack…) |
| `/api/v1/health/ready` | Disponibilité : exécute `SELECT 1` sur PostgreSQL (503 si la base ne répond pas) | Healthcheck de déploiement Railway |

Railway n'utilise le healthcheck qu'au déploiement (bascule du trafic) ;
brancher en plus une supervision externe sur `/api/v1/health`.

## 7. Checklist de durcissement

- [ ] `ENVIRONMENT=production` (active tous les contrôles ci-dessous au démarrage).
- [ ] Secrets forts et uniques (`JWT_SECRET`, clés S3, Mistral, webhook) ;
      jamais dans le dépôt (aucun n'y figure : vérifié dans l'historique git).
- [ ] Paiement `sandbox` refusé en production (automatique) ; `disabled` au lancement.
- [ ] SMS console refusé (automatique) ; fournisseur réel branché.
- [ ] `OTP_TEST_WHITELIST` / `OTP_TEST_CODE` absents (refusés automatiquement
      en production : le mode OTP de test n'existe qu'en staging, §10).
- [ ] HTTPS partout ; HSTS envoyé par l'API et le front ; URL publiques en `https://` (vérifié au démarrage).
- [ ] `CORS_ORIGINS` = origine exacte du front, sans joker (vérifié au démarrage).
- [ ] `TRUSTED_PROXY_HOPS=1` derrière Railway (sinon le rate limiting par IP
      bloquerait tout le monde à la fois ; vérifié au démarrage). Valeur à
      **confirmer par la mesure** après le premier déploiement, avec le
      diagnostic admin du §12.7 (même procédure sur Railway).
- [ ] En-têtes de sécurité (CSP, X-Frame-Options, nosniff, Referrer-Policy,
      Permissions-Policy) : API (middleware) et front (`vercel.json` / `Caddyfile`).
- [ ] Documentation interactive de l'API désactivée (automatique en production).
- [ ] Bucket privé sans aucun accès public ; jeton S3 limité aux deux buckets.
- [ ] Sauvegardes PostgreSQL actives et restauration testée.
- [ ] HSTS `preload` : non activé par défaut (engagement durable à prendre
      sciemment, sous-domaines compris).

## 8. Plus tard

**Paiement en ligne** — point de bascule unique :
`backend/app/services/payment_providers/__init__.py`. Écrire l'adaptateur de
l'agrégateur (contrat `PaymentProvider`), l'ajouter à `Settings.payment_provider`,
puis renseigner `PAYMENT_PROVIDER`, `PAYMENT_WEBHOOK_SECRET` et ses
identifiants, et déclarer chez lui l'URL `https://api.teranga.sn/api/v1/webhooks/payments`.
Aucune ligne du code métier ne change ; le front affiche automatiquement les
moyens en ligne (`GET /payments/options`, `online_available`).

**Clé Mistral** — créer une clé **dédiée à la production** dans la console
Mistral, la renseigner dans `MISTRAL_API_KEY` (Railway), passer
`AI_TRIAGE_PROVIDER=mistral`, puis **révoquer** l'ancienne clé (en particulier
toute clé ayant servi en développement). En cas de fuite : révoquer
immédiatement ; le triage retombe sur l'heuristique sans interruption.

**Montée en charge** — plusieurs instances du backend : `REDIS_URL`
obligatoire (temps réel et tickets partagés, rate limiting commun).

## 9. Essayer Redis et S3 en local (facultatif)

```bash
docker compose -f docker-compose.dev.yml up -d
```

Puis dans `backend/.env` : `REDIS_URL=redis://localhost:6379/0`,
`STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL=http://localhost:9000`,
`S3_REGION=us-east-1`, `S3_ACCESS_KEY_ID=teranga-local`,
`S3_SECRET_ACCESS_KEY=teranga-local-only`, `S3_PRIVATE_BUCKET=teranga-prive`,
`S3_PUBLIC_BUCKET=teranga-public`,
`S3_PUBLIC_BASE_URL=http://localhost:9000/teranga-public`. Retirer ces lignes
pour revenir au fonctionnement local habituel.

## 10. Beta de test (staging)

Objectif : faire essayer l'application à des collaborateurs **avant**
d'avoir un fournisseur SMS, sur une instance séparée de la production.

### 10.1 L'instance

- Un **environnement Railway distinct** (ex. `staging`), avec sa **propre**
  base PostgreSQL, son Redis et ses **propres** buckets : jamais la base ni
  les buckets de production (données de test, documents de test).
- `ENVIRONMENT=staging`, `SMS_PROVIDER=console` (obligatoire avec le mode de
  test, voir ci-dessous), `PAYMENT_PROVIDER=disabled`, URL publiques et
  `CORS_ORIGINS` de l'instance de staging.
- Le front de staging est construit avec le `VITE_API_BASE_URL` du backend
  de staging. Il affiche de lui-même le bandeau « Version de test · données
  temporaires » (d'après `GET /api/v1/meta`, partout sauf en production).

### 10.2 Mode OTP de test

| Variable | Valeur |
|---|---|
| `OTP_TEST_WHITELIST` | Numéros E.164 des testeurs, séparés par des virgules (ex. `+221770000001,+221770000002`). De préférence des numéros dédiés aux tests. |
| `OTP_TEST_CODE` | Le code commun, exactement `OTP_CODE_LENGTH` chiffres (6 par défaut). Tiré au hasard (`python -c "import secrets; print(f'{secrets.randbelow(10**6):06d}')"`), jamais `000000` ni `123456`. |

Pour un numéro de la liste, `request-otp` n'envoie **aucun SMS** : le code à
saisir est `OTP_TEST_CODE`. **Rien d'autre ne change** : le code est haché en
base, à usage unique, expire (`OTP_TTL_SECONDS`), est invalidé après
`OTP_MAX_ATTEMPTS` erreurs, les demandes restent limitées en débit, et la
réponse est identique pour tous les numéros (non-énumération). Un numéro
hors liste suit le flux normal (avec `console`, il ne reçoit rien : seuls les
testeurs listés peuvent se connecter).

Procédure :

1. Collecter les numéros des testeurs ; les écrire dans `OTP_TEST_WHITELIST`.
2. Tirer `OTP_TEST_CODE` ; le transmettre **aux seuls testeurs**, par un canal
   privé (jamais dans un ticket, un dépôt ou un groupe public).
3. Déployer ; vérifier `GET /api/v1/meta` → `"environment": "staging"`,
   `"otp_test_mode": true`. Les journaux montrent
   `[staging] code OTP de test émis…` à chaque demande d'un testeur (sans le
   numéro ni le code).
4. Fin de beta, ou départ d'un testeur : retirer son numéro (ou vider les
   deux variables) et **changer `OTP_TEST_CODE`** si le code a pu circuler.

### 10.3 Pourquoi c'est impossible en production

Deux verrous **indépendants**, chacun prouvé par ses propres tests
(`backend/tests/test_otp_test_mode.py`) et par des tests de mutation (chaque
verrou retiré fait échouer la suite) :

1. **Au démarrage** : avec `ENVIRONMENT=production`, une liste ou un code de
   test fait **refuser le démarrage** (avec les autres problèmes de
   configuration) ; en `development`/`test` aussi. Un mode de test incomplet,
   un code mal formé, un numéro non E.164 ou `SMS_PROVIDER=unconfigured`
   (dont les erreurs révéleraient la liste) sont refusés en staging.
2. **À l'exécution** : même une configuration qui aurait échappé à la
   validation n'a aucun effet hors `ENVIRONMENT=staging` : vrai SMS, code
   aléatoire, code de test refusé.

Et la production exige toujours un vrai fournisseur SMS (§0, bloquant n°1) :
le mode de test ne le remplace pas.

## 11. Application installable (PWA)

Le front est installable comme une application, en plein écran :

- **Android (Chrome)** : menu ⋮ > « Installer l'application », ou le bouton
  « Installer » du conseil « Installer l'app » (écran Profil).
- **iPhone / iPad (Safari)** : bouton Partager > « Sur l'écran d'accueil »
  (expliqué dans le même conseil). L'icône et le nom « Téranga » viennent de
  `apple-touch-icon` et des balises `apple-mobile-web-app-*` d'`index.html`.

Pièces : `frontend/public/manifest.webmanifest`, `frontend/public/icons/`
(régénérables : `uv run --no-project --with pillow python
frontend/scripts/generate_pwa_icons.py`), service worker `frontend/pwa/sw.js`
(versionné au build en `dist/sw.js` par `frontend/pwa/serviceWorkerPlugin.ts`).

Ce que fait le service worker, et surtout ce qu'il ne fait pas :

- pages : **réseau d'abord**, toujours ; la coquille en cache ne sert que
  hors connexion ;
- fichiers hachés `/assets/*` : cache d'abord (immuables par construction) ;
- **jamais** l'API, une requête authentifiée, non-GET ou d'une autre origine
  (documents d'identité compris), ni une réponse `no-store`/`private`/en erreur ;
- chaque déploiement produit une nouvelle version : elle s'installe seule,
  prend la main tout de suite et supprime les anciens caches.

En-têtes requis (déjà en place, testés) : `sw.js` et le manifeste en
`Cache-Control: no-cache`, manifeste en `application/manifest+json`
(`vercel.json`, `Caddyfile`).

**Désactiver le service worker en urgence** : remplacer `frontend/pwa/sw.js`
par un script qui se désinscrit (`self.addEventListener('install', () =>
self.skipWaiting()); self.addEventListener('activate', (e) =>
e.waitUntil(self.registration.unregister()));`) et redéployer : chaque
appareil le récupère à sa prochaine visite (sw.js n'est jamais mis en cache).

## 12. Render + Supabase + Vercel (beta staging)

Second chemin de déploiement, **indépendant** du runbook Railway ci-dessus
(qui reste valable tel quel) : backend sur **Render**, base PostgreSQL +
PostGIS et fichiers sur **Supabase**, front sur **Vercel**. Cible : la beta
de test (§10), `ENVIRONMENT=staging`, espèces seulement, connexion par OTP de
test. Le développement local n'est pas concerné : sans ces variables, tout
tourne comme avant.

Pièces du dépôt : `render.yaml` (Blueprint Render), `backend/scripts/serve.py`
(démarrage), `frontend/vercel.json` (déjà utilisé, §4.5).

### 12.1 Topologie

```
Navigateur ──HTTPS──▶ Vercel : front statique (frontend/, vercel.json)
     │
     └──HTTPS / WSS──▶ Render : backend FastAPI (image backend/Dockerfile,
                       démarrage scripts/serve.py)
                          ├── Supabase Postgres + PostGIS (session pooler, port 5432, TLS)
                          └── Supabase Storage (API S3, path-style)
                                 ├── bucket PRIVÉ  : documents d'identité, pièces jointes
                                 └── bucket PUBLIC : photos de profil et de couverture
```

Pas de Redis : le rate limiting passe par PostgreSQL (`RATE_LIMIT_BACKEND`
vide), le temps réel tient sur l'instance unique (`WEB_CONCURRENCY=1`).

### 12.2 Limites des offres gratuites (à connaître avant d'inviter des testeurs)

| Limite | Conséquence | Parade |
|---|---|---|
| **Render free : mise en veille après ~15 min sans trafic** | La première requête qui réveille le service attend son démarrage (souvent 30 s à 1 min) ; le front abandonne une requête au bout de 10 s (« Impossible de contacter le serveur ») | Recharger la page après quelques secondes ; ou une sonde externe gratuite (UptimeRobot, Better Stack) sur `GET /api/v1/health` toutes les 10 min, qui garde le service éveillé (un seul service gratuit tient dans les 750 h/mois offertes) |
| **Render free : ni shell, ni pré-déploiement, ni tâche planifiée** | Migrations au démarrage (`serve.py`) ; seed et admin depuis votre poste (§12.6) | — |
| **Render : disque éphémère** | Rien n'est écrit sur le disque du service | `STORAGE_BACKEND=s3` (fixé dans `render.yaml`) |
| **Supabase free : projet mis en pause après ~7 jours sans activité** | Le backend ne joint plus la base (`/health/ready` en 503) | Le relancer depuis le tableau de bord Supabase ; une sonde (ligne 1) l'évite tant que le service répond |
| **Supabase : connexions du pooler limitées** (taille du pool : *Database > Settings*) | Le backend ouvre jusqu'à 15 connexions (pool SQLAlchemy 5 + 10) ; au-delà de la taille du pool, erreur « max clients » | Suffisant pour une beta ; garder `WEB_CONCURRENCY=1` |
| **`expire_requests.py` non planifié** | Rien de bloquant : la règle d'expiration des demandes s'applique déjà sans lui (§4.8) | Le lancer de temps en temps depuis votre poste (§12.6) |

### 12.3 Variables d'environnement

**Backend (Render).** Les valeurs « fixée » sont écrites dans `render.yaml`
(comportement de la beta) ; les autres sont demandées par Render à la
création du Blueprint (`sync: false`), puis modifiables dans *Environment*.

| Variable | Valeur pour cette pile | Source |
|---|---|---|
| `ENVIRONMENT` | `staging` | fixée |
| `SMS_PROVIDER` | `console` (obligatoire avec le mode OTP de test, §10.2 ; aucun code n'est journalisé hors dev) | fixée |
| `PAYMENT_PROVIDER` | `disabled` (espèces seulement) | fixée |
| `STORAGE_BACKEND` | `s3` (couvre aussi photos et pièces jointes) | fixée |
| `WEB_CONCURRENCY` | `1` | fixée |
| `JWT_SECRET` | aléatoire, 256 bits | générée par Render |
| `DATABASE_URL` | session pooler Supabase, §12.4 | à saisir |
| `FRONTEND_PUBLIC_BASE_URL` | `https://<projet>.vercel.app` | à saisir |
| `BACKEND_PUBLIC_BASE_URL` | `https://teranga-backend.onrender.com` (URL affichée par Render) | à saisir |
| `CORS_ORIGINS` | `https://<projet>.vercel.app` (origine exacte, sans `/` final) | à saisir |
| `TRUSTED_PROXY_HOPS` | `1` au premier déploiement, **puis la valeur mesurée** (§12.7) | à saisir |
| `S3_ENDPOINT_URL` | `https://<ref>.storage.supabase.co/storage/v1/s3` | à saisir |
| `S3_REGION` | région affichée par Supabase (*Storage > S3 Configuration*), ex. `eu-central-1` | à saisir |
| `S3_ACCESS_KEY_ID` / `S3_SECRET_ACCESS_KEY` | clé d'accès S3 Supabase (§12.4) | à saisir |
| `S3_PRIVATE_BUCKET` | `teranga-prive` | à saisir |
| `S3_PUBLIC_BUCKET` | `teranga-public` | à saisir |
| `S3_PUBLIC_BASE_URL` | `https://<ref>.supabase.co/storage/v1/object/public/teranga-public` | à saisir |
| `OTP_TEST_WHITELIST` | numéros E.164 des testeurs (§10.2) | à saisir |
| `OTP_TEST_CODE` | code tiré au hasard, 6 chiffres (§10.2) | à saisir |

Laisser **absentes** (défaut sûr) : `S3_FORCE_PATH_STYLE` (path-style activé
automatiquement par `S3_ENDPOINT_URL`), `REDIS_URL`, `RATE_LIMIT_BACKEND`,
`PORT` (fourni par Render), `AI_TRIAGE_PROVIDER` (heuristique sans clé),
`*_STORAGE_BACKEND` (héritent de `STORAGE_BACKEND`).

**Front (Vercel).** `VITE_API_BASE_URL=https://teranga-backend.onrender.com/api/v1`
(figée au build : la changer impose de redéployer le front).

### 12.4 Supabase

**Projet.** Région **Francfort (eu-central-1)**, la même que le service Render
(`region: frankfurt` dans `render.yaml`) : chaque requête SQL fait
l'aller-retour, la distance compte.

**DATABASE_URL — session pooler, port 5432.** Dans *Connect*, copier la chaîne
**Session pooler** et la convertir ainsi :

```
# Copiée depuis Supabase :
postgresql://postgres.<ref>:<MOT_DE_PASSE>@aws-<n>-<region>.pooler.supabase.com:5432/postgres
# À renseigner (driver asyncpg + TLS exigé) :
postgresql+asyncpg://postgres.<ref>:<MOT_DE_PASSE>@aws-<n>-<region>.pooler.supabase.com:5432/postgres?ssl=require
```

- Utilisateur `postgres.<ref>` (avec le suffixe du projet), port **5432**.
- Mot de passe : celui de la base, défini à la création du projet. S'il
  contient des caractères spéciaux (`@`, `:`, `/`, `#`, `%`…), les encoder en
  URL (`python -c "import urllib.parse; print(urllib.parse.quote('<mdp>', safe=''))"`).
- `?ssl=require` : la connexion est refusée si elle n'est pas chiffrée.
- **Pourquoi pas le port 6543 (transaction pooler)** : il n'accepte pas les
  instructions préparées qu'asyncpg utilise pour chaque requête (erreurs
  aléatoires « prepared statement … does not exist »), et ne garde pas une
  même connexion serveur d'une transaction à l'autre (le verrou des
  migrations de `serve.py` n'y tiendrait pas). Cette URL est **refusée au
  démarrage** avec un message explicite.
- **Pourquoi pas la connexion directe** (`db.<ref>.supabase.co`) : elle n'est
  joignable qu'en IPv6 sur l'offre gratuite, que Render ne sait pas joindre.

**PostGIS.** Ne rien faire à la main : la première migration exécute
`CREATE EXTENSION IF NOT EXISTS postgis`. Après le premier déploiement, dans
*SQL Editor* : `SELECT postgis_full_version();` doit répondre.

**API de données Supabase : à DÉSACTIVER (obligatoire).** Supabase expose
par défaut le schéma `public` via son API REST (PostgREST), accessible avec
la clé `anon` du projet. Nos migrations créent toutes les tables dans
`public` (utilisateurs, téléphones, codes OTP hachés, métadonnées des
documents…) **sans RLS** : l'application n'utilise pas cette API, qui doit
donc être fermée.

1. *Project Settings > Data API* : désactiver l'API de données (ou retirer
   `public` des schémas exposés).
2. Défense en profondeur, dans *SQL Editor* :
   ```sql
   REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
   REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;
   REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon, authenticated;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon, authenticated;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM anon, authenticated;
   ```
   À relancer après chaque migration qui ajoute une table si les privilèges
   par défaut ont été modifiés depuis.
3. Vérifier (clé `anon` : *Project Settings > API Keys*) :
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" \
     "https://<ref>.supabase.co/rest/v1/user?select=id&limit=1" \
     -H "apikey: <CLE_ANON>" -H "Authorization: Bearer <CLE_ANON>"
   ```
   Attendu : **pas 200** (404 si l'API est désactivée, 401/403 sinon).
   Un 200 signifie que les tables sont lisibles publiquement : ne pas inviter
   de testeurs avant d'avoir corrigé.

**Storage.**

1. *Storage* : créer `teranga-prive` (**Public : désactivé**) et
   `teranga-public` (**Public : activé**). Deux buckets différents sont exigés
   au démarrage : une CNI ne peut pas atterrir dans le bucket public.
2. *Storage > S3 Configuration* : noter l'endpoint et la région ; créer une
   **clé d'accès S3** → `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`. Cette clé
   contourne la RLS et donne accès à tous les buckets : uniquement dans les
   variables de Render, jamais dans le front ni dans un fichier.
3. Adressage : Supabase exige le path-style
   (`https://<ref>.storage.supabase.co/storage/v1/s3/<bucket>/<clé>`). Il est
   **activé automatiquement** dès que `S3_ENDPOINT_URL` est renseigné
   (`S3_FORCE_PATH_STYLE`, testé).
4. Photos de profil : servies par
   `S3_PUBLIC_BASE_URL/profile-media/<clé>`, soit
   `https://<ref>.supabase.co/storage/v1/object/public/teranga-public/profile-media/<clé>`
   (autorisé par la CSP du front, `img-src https:`). Les documents d'identité
   n'ont **aucune** URL publique : ils ne sortent que par les endpoints
   authentifiés du backend.

### 12.5 Pas-à-pas

1. **Supabase** : créer le projet (Francfort), désactiver l'API de données
   et vérifier (§12.4), créer les deux buckets et la clé S3.
2. **Migrations, depuis votre poste**, contre Supabase (facultatif : le
   démarrage Render les applique de toute façon ; utile pour vérifier la
   connexion avant de déployer) — §12.6 :
   `uv run alembic upgrade head`.
3. **Render** : *New > Blueprint*, choisir le dépôt ; Render lit
   `render.yaml` et demande les variables `sync: false` (§12.3). Pour
   `TRUSTED_PROXY_HOPS`, saisir `1` (valeur provisoire, §12.7). Au
   démarrage, les journaux montrent :
   ```
   Migrations : alembic upgrade head (sous verrou)...
   Migrations à jour. Démarrage d'uvicorn sur 0.0.0.0:<PORT>.
   ```
   Une configuration incomplète arrête le démarrage avec la liste des
   variables en cause (aucune valeur secrète affichée) ; une migration en
   échec aussi. Dans les deux cas, la version précédente reste en service.
4. **Données de référence, depuis votre poste** (§12.6) :
   `uv run python scripts/seed_reference.py`.
5. **Vercel** : *Add New > Project*, même dépôt, **Root Directory =
   `frontend`** (framework Vite détecté, `vercel.json` appliqué), variable
   `VITE_API_BASE_URL` (§12.3). Reporter l'URL obtenue dans
   `FRONTEND_PUBLIC_BASE_URL` et `CORS_ORIGINS` côté Render (le service
   redémarre). Les déploiements *Preview* de Vercel ont une autre origine :
   refusée par CORS, c'est voulu (seule l'URL de production de la beta parle
   au backend).
6. **Premier administrateur** : la personne s'inscrit sur le site avec un
   numéro de la liste de test et le code de test (§10.2), puis, depuis votre
   poste (§12.6) : `uv run python scripts/create_admin.py +221XXXXXXXXX`.
7. **Mesurer `TRUSTED_PROXY_HOPS`** (§12.7), le corriger dans Render.
8. **Test de fumée** (§12.8).

Mises à jour ensuite : un push sur `main` modifiant `backend/` redéploie le
backend (`buildFilter` de `render.yaml`) ; Vercel redéploie le front. Les
migrations passent au démarrage, sous verrou.

### 12.6 Seed, admin et migrations sans shell (depuis votre poste)

Render gratuit n'a pas de shell ; Supabase est joignable de partout : les
scripts tournent sur votre poste, avec `DATABASE_URL` pointée **pour la seule
commande** vers le session pooler (§12.4). Le reste de votre `backend/.env`
de développement est sans effet sur ces scripts.

Bash (Git Bash, macOS, Linux), depuis `backend/` :

```bash
export DATABASE_URL='postgresql+asyncpg://postgres.<ref>:<MDP>@aws-<n>-<region>.pooler.supabase.com:5432/postgres?ssl=require'
uv run alembic upgrade head                          # facultatif (fait au démarrage Render)
uv run python scripts/seed_reference.py              # métiers + taux initial ; --rate-bps 0 pour 0 %
uv run python scripts/create_admin.py +221XXXXXXXXX  # après l'inscription de la personne
uv run python scripts/expire_requests.py             # facultatif, de temps en temps
unset DATABASE_URL                                   # retour à la base locale
```

PowerShell, depuis `backend\` :

```powershell
$env:DATABASE_URL = 'postgresql+asyncpg://postgres.<ref>:<MDP>@aws-<n>-<region>.pooler.supabase.com:5432/postgres?ssl=require'
uv run python scripts/seed_reference.py
uv run python scripts/create_admin.py +221XXXXXXXXX
Remove-Item Env:DATABASE_URL
```

- `seed_reference.py` et `create_admin.py` **affichent la base visée**
  (hôte, port, base ; jamais le mot de passe) avant d'agir : vérifier qu'il
  s'agit bien de Supabase (`create_admin.py` demande en plus confirmation).
- Ces scripts sont **idempotents** : les relancer ne duplique rien.
- `scripts/seed.py` (données de **démonstration** : faux artisans, faux avis)
  **refuse** de s'exécuter contre une base non locale ou hors
  development/test : il ne peut pas polluer la beta, même par erreur.
- Une variable d'environnement prime sur `backend/.env` : penser à la retirer
  (`unset` / `Remove-Item`) pour retrouver la base locale.

Proposition (non activée) : semer les données de référence au démarrage
serait sûr (script idempotent, sans aucune donnée de démonstration), mais le
taux de commission initial deviendrait implicite. La commande unique ci-dessus
reste explicite et journalisée ; à reconsidérer si les redéploiements à zéro
se multiplient.

### 12.7 Mesurer TRUSTED_PROXY_HOPS (obligatoire)

Le rate limiting par IP (OTP, triage IA) lit l'adresse du client dans
`X-Forwarded-For`, à `TRUSTED_PROXY_HOPS` crans **en partant de la droite**
(`backend/app/core/client_ip.py`). Render ne documente pas le nombre de proxys
qui s'ajoutent à la chaîne, et les relevés publiés divergent (1, 2 ou 3). Une
valeur trop basse met tous les testeurs dans **un seul compteur** (quelques
demandes de code bloquent tout le monde) ; trop haute, elle laisse un client
**falsifier** son adresse. Il faut donc la mesurer, une fois :

1. Connecté en admin, ouvrir
   `https://teranga-backend.onrender.com/api/v1/admin/diagnostics/client-ip`
   (avec le jeton : depuis l'onglet Réseau du navigateur, ou
   `curl -H "Authorization: Bearer <jeton>" …`). Réponse :
   ```json
   {"peer": "10.x.x.x", "x_forwarded_for": ["<A>", "<B>", "<C>"],
    "trusted_proxy_hops": 1, "client_ip": "<C>"}
   ```
2. Comparer avec votre adresse publique (ex. `curl https://ifconfig.me`) :
   sa position **en partant de la droite** dans `x_forwarded_for` (1 = la
   dernière) est la bonne valeur. Exemple : votre IP est `<B>` → `2`.
3. La reporter dans `TRUSTED_PROXY_HOPS` (Render redémarre), puis vérifier
   que `client_ip` est bien votre adresse. Refaire la mesure depuis un
   deuxième réseau (4G) : `client_ip` doit changer avec lui.

### 12.8 Test de fumée (beta)

- [ ] `GET https://teranga-backend.onrender.com/api/v1/health/ready` → 200.
- [ ] `GET /api/v1/meta` → `{"environment": "staging", "otp_test_mode": true}`.
- [ ] Le front Vercel s'ouvre, bandeau « Version de test » visible ; une page
      profonde rechargée (`/recherche`) s'affiche.
- [ ] Un numéro de la liste se connecte avec le code de test ; un numéro hors
      liste ne reçoit rien (réponse identique).
- [ ] `SELECT postgis_full_version();` répond ; recherche par proximité OK.
- [ ] API de données Supabase fermée (commande `curl` du §12.4 : pas 200).
- [ ] Un artisan envoie une pièce d'identité : l'objet est dans
      `teranga-prive` (*Storage*), jamais dans `teranga-public` ; l'admin la
      voit dans `/admin/verifications`.
- [ ] Une photo de profil s'affiche depuis `…/object/public/teranga-public/…`.
- [ ] Messagerie : un message arrive en temps réel chez l'autre partie (WSS).
- [ ] `client_ip` du diagnostic = votre adresse (§12.7).
- [ ] Paiement : seule l'option espèces est proposée.
