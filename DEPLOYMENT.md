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
OTP (`OTP_*`, `RATE_LIMIT_OTP_*`), JWT (`JWT_ACCESS_TTL_SECONDS`,
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
- [ ] HTTPS partout ; HSTS envoyé par l'API et le front ; URL publiques en `https://` (vérifié au démarrage).
- [ ] `CORS_ORIGINS` = origine exacte du front, sans joker (vérifié au démarrage).
- [ ] `TRUSTED_PROXY_HOPS=1` derrière Railway (sinon le rate limiting par IP
      bloquerait tout le monde à la fois ; vérifié au démarrage).
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
