# Téranga Services

Plateforme sénégalaise de mise en relation entre particuliers et artisans qualifiés (plomberie, électricité, climatisation, etc.).

## Fonctionnalités

- **Recherche & découverte** — recherche filtrée d'artisans par métier, note et disponibilité.
- **Diagnostic assisté par IA** — description d'un problème (texte, photo, vocal) analysée via Gemini, avec repli automatique sur une heuristique par mots-clés si aucune clé API n'est configurée.
- **Messagerie & devis** — chat client ↔ artisan avec envoi et acceptation de devis.
- **Tableau de bord artisan** — suivi des revenus, des demandes entrantes et des indicateurs de performance.
- **Profils** — fiches artisan détaillées (avis, réalisations, statistiques) et profil client avec moyens de paiement locaux (Wave, Orange Money, carte).

## Stack technique

| Côté | Technologies |
| --- | --- |
| Frontend | React 19, TypeScript, Tailwind CSS v4, Vite |
| Backend | Express, middleware Vite (dev), Google Gemini (`@google/genai`) |
| Qualité | Vitest, Testing Library, ESLint, Prettier |

## Structure du projet

```
src/
├── App.tsx                       # State machine racine (vue courante) + état global
├── index.css                     # Tailwind + design tokens (@theme) + classes utilitaires custom
├── types.ts                      # Types du domaine
├── data/                         # Données de démonstration (mock)
└── components/
    ├── Header.tsx, BottomNav.tsx      # Navigation persistante
    ├── LandingScreen.tsx              # Accueil / choix de rôle
    ├── ClientHomeScreen.tsx           # Accueil client
    ├── DescribeProblemScreen.tsx      # Diagnostic IA
    ├── SearchScreen.tsx               # Recherche d'artisans
    ├── ArtisanProfileScreen.tsx       # Fiche artisan
    ├── ChatScreen.tsx                 # Messagerie + devis
    ├── ArtisanDashboardScreen.tsx     # Tableau de bord artisan
    ├── UserProfileScreen.tsx          # Profil client
    └── ui/SafeImage.tsx               # Image avec repli sur erreur de chargement
```

## Développement local

**Prérequis :** Node.js LTS (v20+) et git.

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
