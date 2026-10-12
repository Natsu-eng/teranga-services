# Téranga Services — Frontend

Application web (SPA) de Téranga Services. C'est le service `frontend/` du monorepo — voir le [README racine](../README.md) pour la présentation du produit et la topologie complète (frontend + backend FastAPI).

Projet **Vite pur** : aucun serveur Node ne tourne côté front, ni en dev (serveur Vite) ni en production (fichiers statiques). Toute la logique métier, l'IA de triage et les secrets vivent dans le backend FastAPI.

## Stack technique

| Côté | Technologies |
| --- | --- |
| Frontend | React 19, TypeScript, Tailwind CSS v4, React Router 7, Vite |
| Qualité | Vitest, Testing Library, ESLint, Prettier |

Dépendances embarquées dans le bundle : `react`, `react-dom`, `react-router`, `lucide-react`. Tout le reste (Vite, Tailwind, outillage de test) est une dépendance de build.

## Structure du projet

```text
frontend/
├── src/
│   ├── App.tsx                       # Routes (React Router) et layouts
│   ├── index.css                     # Tailwind + design tokens (@theme) + classes utilitaires custom
│   ├── types/                        # Types du domaine
│   ├── data/                         # Données fictives — réservées aux tests
│   ├── lib/api/                      # Accès aux données : contrat ApiClient, client HTTP, mock de test
│   ├── lib/realtime/                 # Transport temps réel (WebSocket, reconnexion, statut de repli)
│   ├── components/                   # Composants partagés (layout, ui)
│   └── features/                     # Écrans et hooks, organisés par domaine
├── public/                           # Assets statiques servis tels quels
├── vite.config.ts                    # Proxy /api/v1 (dev/preview), port 3000
├── vercel.json                       # Production : fallback SPA, en-têtes de sécurité, cache
└── index.html
```

## Développement local — lancer les deux services

Le front (ce dossier) et le backend FastAPI (`../backend/`) sont **deux
process séparés**, dans deux terminaux. Le front appelle toujours
`/api/v1/...` en relatif ; en dev, c'est **le proxy de Vite**
(`vite.config.ts`) qui route ces requêtes vers le backend.

**Prérequis :** Node.js LTS (v20+), git, et le backend installé (voir
[backend/README.md](../backend/README.md)).

**Terminal 1 — backend :**

```bash
cd backend
uv run alembic upgrade head        # une fois, ou après une nouvelle migration
uv run python scripts/seed.py      # une fois, idempotent — données de dev
uv run uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend**, depuis ce dossier (`frontend/`) :

1. Installer les dépendances : `npm ci` (ou `npm install` pour mettre à jour le lockfile)
2. (Optionnel) Copier [.env.example](.env.example) vers `.env.local` si le backend n'écoute pas sur `http://localhost:8000`.
3. Lancer Vite : `npm run dev` → <http://localhost:3000> (HMR), `/api/v1/*` proxifié vers `BACKEND_URL`.
4. Avant de commit/push : `npm run validate` (typecheck + lint + tests).

En dev, les codes OTP ne sont pas envoyés par SMS : ils s'affichent dans la
console du terminal backend (`ConsoleSmsProvider`, voir
[backend/README.md](../backend/README.md#authentification-téléphone--otp)).

Le port 3000 est fixe (`strictPort`) : c'est l'origine autorisée par
`CORS_ORIGINS` côté backend. S'il est déjà pris, Vite s'arrête avec une
erreur au lieu de basculer en silence sur un autre port.

## Production

Runbook complet (variables, étapes, durcissement) : [DEPLOYMENT.md](../DEPLOYMENT.md).
Deux hébergements prêts : **Vercel** ([vercel.json](vercel.json)) ou
**Railway** ([Dockerfile](Dockerfile) : build Vite puis Caddy,
[Caddyfile](Caddyfile), [railway.json](railway.json)). Les en-têtes de
sécurité des deux sont identiques (test `src/deploymentConfig.test.ts`).
`VITE_API_BASE_URL` est figée **au build** : sur Railway, la déclarer dans
les variables du service (transmise au Dockerfile en argument de build).

Lancement **espèces seulement** (`PAYMENT_PROVIDER=disabled` côté backend) :
l'écran de paiement ne propose que les espèces, sans promesse de séquestre,
et aucun bouton « payer en ligne » n'apparaît (`PaymentSummary.onlineAvailable`).

`npm run build` produit **uniquement des fichiers statiques** dans `dist/`
(`index.html` + `assets/` hachés). N'importe quel hébergeur statique les
sert ; deux réglages sont indispensables :

1. **Fallback SPA** : toute route inconnue hors `/api/` doit renvoyer
   `index.html` (sinon un rechargement sur `/artisans/123` donne un 404).
2. **Accès à l'API**, au choix :
   - **Deux origines (cible : Vercel + Railway, recommandé)** — builder avec
     `VITE_API_BASE_URL=https://<backend>/api/v1` et ajouter l'origine exacte
     du front à `CORS_ORIGINS` côté backend. Les jetons passent par l'en-tête
     `Authorization` (pas de cookie), donc rien d'autre à configurer.
   - **Même origine** — laisser `VITE_API_BASE_URL` vide et placer devant le
     front un reverse proxy qui route `/api/v1/*` vers le backend, **y compris
     la mise à niveau WebSocket** de `/api/v1/realtime/ws` (sans elle, la
     messagerie fonctionne quand même, en relecture REST toutes les 5 s).

**Vercel** (Root Directory = `frontend`) : [vercel.json](vercel.json) porte
déjà le fallback SPA, le cache immuable des assets et les en-têtes de
sécurité (CSP, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`,
`Permissions-Policy` caméra/micro/géolocalisation limités au site).
Renseigner `VITE_API_BASE_URL` dans les variables d'environnement du projet.

**Tester le build en local** : `npm run build && npm run preview` sert
`dist/` sur <http://localhost:3000> avec le même proxy `/api/v1` et **les
mêmes en-têtes que la production** (relus depuis `vercel.json`) — une CSP
trop stricte se voit donc avant le déploiement.

## Variables d'environnement

| Variable | Lue par | Description |
| --- | --- | --- |
| `BACKEND_URL` | `vite.config.ts` (Node, dev/preview) | Origine du backend vers laquelle le proxy route `/api/v1/*`. Défaut `http://localhost:8000`. Validée au démarrage. Jamais envoyée au navigateur. |
| `VITE_API_BASE_URL` | bundle navigateur (figée au build) | Base de l'API. Vide = `/api/v1` même origine. URL absolue http(s) en déploiement multi-origines. Validée au chargement ([base-url.ts](src/lib/api/base-url.ts)). **Publique** : n'y mettre aucun secret. |

Le front ne détient **aucun secret** : la configuration IA (`AI_TRIAGE_PROVIDER`,
`MISTRAL_API_KEY`) est exclusivement côté backend. Voir [.env.example](.env.example).

## Messagerie temps réel (`src/lib/realtime`, `src/features/messages`)

- **REST reste la source de vérité** : l'envoi d'un message (texte ou photo)
  passe toujours par `POST /conversations/{id}/messages[/image]`, que le
  temps réel soit disponible ou non.
- **Un seul WebSocket par onglet** (`RealtimeProvider`, client ou artisan
  connecté uniquement), URL dérivée de `VITE_API_BASE_URL`
  ([url.ts](src/lib/realtime/url.ts)) : `wss://` dès que la page ou l'API est
  en https. Authentification par **ticket à usage unique** (60 s) demandé à
  `POST /realtime/ticket`, transmis en sous-protocole — jamais dans l'URL,
  jamais de cookie (pas de détournement de WebSocket intersite possible).
- **Repli automatique** : tant que le statut n'est pas `open`, le fil ouvert
  relit `?since=` toutes les 5 s et le badge de non-lus toutes les 30 s ;
  reconnexion à backoff exponentiel (1 s → 30 s) ; rattrapage à chaque
  reconnexion et retour au premier plan ; **tout s'arrête** quand l'onglet
  passe en arrière-plan. Réglages : [config.ts](src/lib/realtime/config.ts).
- **Envoi optimiste** : le message s'affiche aussitôt (« Envoi… »), est
  remplacé par la version enregistrée (éventuellement masquée), ou reste
  visible en échec avec la raison, « Réessayer » et « Supprimer ».
- **Photos** : chargées en blob avec le jeton d'accès, URL locale révoquée
  ensuite ; jamais d'URL publique.

En dev, le proxy Vite transmet aussi le WebSocket (`ws: true`). En
production, la CSP de [vercel.json](vercel.json) autorise `connect-src`
`https:` et `wss:`.

## Paiements (`src/features/payments`)

- **Le front n'envoie jamais de montant** : `initPayment(interventionId,
  channel)` ; le serveur applique le prix du devis accepté. Aucun montant
  n'est calculé côté front (total, commission, net viennent du serveur).
- **Redirection vers le fournisseur** limitée aux URL `http(s)` absolues
  ([externalNavigation.ts](src/lib/externalNavigation.ts)) — jamais un
  `javascript:` ou un schéma inattendu, même renvoyé par le serveur.
- **Retour du fournisseur** (`/paiement/:id?retour=succes|echec`) : la
  confirmation arrivant par webhook, l'écran relit l'état toutes les 3 s
  pendant 2 min au plus, puis l'annonce honnêtement.
- **Transparence par rôle** (`MoneyBreakdown`) : le client voit « Total à
  payer » et l'absence de frais ajoutés ; l'artisan voit prix, commission
  (taux figé) et « Vous recevez ».

## Back-office admin (`src/features/admin`)

- **Une coquille, une garde** : `/admin/*` est une route imbriquée sous
  `RequireAdminRoute` > `AdminLayout` (en-tête + huit sections). Un
  non-admin voit la 404 standard sur chacune d'elles.
- **Le serveur décide, l'écran informe** : les garde-fous (anti-verrouillage
  du rôle admin, motif obligatoire, plafond de taux) sont affichés avant
  l'action et revérifiés par le serveur ; son refus s'affiche tel quel dans
  la feuille de confirmation (`ConfirmActionSheet`).
- **Accès HTTP** : [admin-backoffice.ts](src/lib/api/admin-backoffice.ts),
  fusionné dans `httpApiClient` ; son contrat `AdminBackofficeApi` fait
  partie d'`ApiClient` (un oubli ne compile pas).
- **Espace Pro** : bandeau de suspension (avec motif) et section « Avis
  reçus » (signalement unique, motif obligatoire).

## Accès aux données (`src/lib/api`)

`api` (index.ts) **est** `httpApiClient` : il implémente tout le contrat
`ApiClient`, vérifié à la compilation. Il n'existe plus de repli méthode par
méthode sur le mock — une méthode ajoutée au contrat sans implémentation
HTTP ne compile pas, et une fonctionnalité dont le backend n'existe pas
encore doit lever explicitement `notImplemented()` (erreur `not_implemented`,
message affichable), jamais renvoyer des données fictives. `mock.ts` et
`data/mockData.ts` sont réservés aux tests : ESLint (`no-restricted-imports`)
refuse tout import depuis le code de production.

## Scripts disponibles

| Commande | Description |
| --- | --- |
| `npm run dev` | Serveur de développement Vite (HMR, proxy `/api/v1`) |
| `npm run build` | Build de production statique (`dist/`) |
| `npm run preview` | Sert `dist/` en local avec proxy et en-têtes de production |
| `npm run typecheck` | Vérification TypeScript sans émission |
| `npm run lint` | Lint ESLint |
| `npm run format` | Formatage Prettier |
| `npm test` | Tests unitaires (Vitest) |
| `npm run validate` | Porte de validation complète (typecheck + lint + test) |
| `npm run clean` | Supprime `dist/` |
