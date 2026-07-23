# Téranga Services — Frontend

Application web (SPA) de Téranga Services. C'est le service `frontend/` du monorepo — voir le [README racine](../README.md) pour la présentation du produit et la topologie complète (frontend + backend FastAPI à venir).

## Stack technique

| Côté | Technologies |
| --- | --- |
| Frontend | React 19, TypeScript, Tailwind CSS v4, Vite |
| Serveur (transitoire) | Express, middleware Vite (dev), Google Gemini (`@google/genai`) — sera retiré une fois la migration vers FastAPI terminée |
| Qualité | Vitest, Testing Library, ESLint, Prettier |

## Structure du projet

```text
frontend/
├── src/
│   ├── App.tsx                       # State machine racine (vue courante) + état global
│   ├── index.css                     # Tailwind + design tokens (@theme) + classes utilitaires custom
│   ├── types/                        # Types du domaine
│   ├── data/                         # Données de démonstration (mock)
│   ├── lib/api/                      # Couche d'accès aux données (interface + implémentation mock)
│   ├── components/                   # Composants partagés (layout, ui)
│   └── features/                     # Écrans et hooks, organisés par domaine
├── public/                           # Assets statiques servis tels quels
├── server.ts                         # Serveur Express (transitoire)
└── index.html
```

## Développement local

**Prérequis :** Node.js LTS (v20+) et git.

Toutes les commandes ci-dessous s'exécutent depuis ce dossier (`frontend/`).

1. Installer les dépendances :
   `npm install`
2. (Optionnel) Copier [.env.local.example](.env.local.example) vers `.env.local` et y renseigner
   votre clé `GEMINI_API_KEY`. Sans clé (ou fichier absent), le serveur fonctionne quand même :
   `/api/analyze-problem` bascule automatiquement sur une heuristique par mots-clés au lieu
   d'appeler Gemini.
3. Lancer le serveur de développement (Express + middleware Vite, avec HMR) :
   `npm run dev`
   L'application est servie sur http://localhost:3000.
4. Avant de commit/push, faire passer la porte de validation unique (typecheck + lint + tests) :
   `npm run validate`

## Variables d'environnement

| Variable | Requise | Description |
| --- | --- | --- |
| `GEMINI_API_KEY` | Non | Clé API Google Gemini pour `/api/analyze-problem`. Sans clé valide, repli automatique sur une heuristique par mots-clés. |

Voir [.env.example](.env.example) et [.env.local.example](.env.local.example) pour le détail. `.env.local` est ignoré par git et prioritaire sur `.env` (voir `server.ts`).

## Scripts disponibles

| Commande | Description |
| --- | --- |
| `npm run dev` | Serveur de développement (Express + Vite middleware, HMR) |
| `npm run build` | Build de production (Vite + bundle serveur esbuild) |
| `npm start` | Démarre le build de production |
| `npm run typecheck` | Vérification TypeScript sans émission |
| `npm run lint` | Lint ESLint |
| `npm run format` | Formatage Prettier |
| `npm test` | Tests unitaires (Vitest) |
| `npm run validate` | Porte de validation complète (typecheck + lint + test) |
