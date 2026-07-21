# AUDIT — Téranga Services

Date : 2026-07-21
Type : audit technique en lecture seule (aucun fichier du projet n'a été modifié).

---

## 1. Inventaire complet

### 1.1 Arborescence

```
teranga-services/
├── .env.example              # Template de secrets (GEMINI_API_KEY, APP_URL)
├── .gitignore                # Pas de dépôt git initialisé (confirmé : pas de .git)
├── README.md                 # Instructions AI Studio génériques
├── assets/.aistudio/.gitignore
├── bun.lock                  # Fichier VIDE (0 octet) — lockfile non généré
├── index.html                # Point d'entrée HTML, charge Google Fonts + Material Symbols
├── metadata.json             # Métadonnées AI Studio (permissions caméra/micro/géoloc, capacité Gemini)
├── package.json
├── server.ts                 # Serveur Express unique, toutes les routes + middleware Vite
├── src/
│   ├── App.tsx                        # State machine racine (currentView) + state global
│   ├── main.tsx                       # Bootstrap React (StrictMode)
│   ├── index.css                      # Tailwind + classes utilitaires custom (icônes, glass, ombre)
│   ├── types.ts                       # Tous les types TS du domaine
│   ├── data/
│   │   └── mockData.ts                # 100% des données (artisans, demandes, messages)
│   └── components/
│       ├── Header.tsx                 # Barre sup. persistante (sauf landing)
│       ├── BottomNav.tsx              # Nav basse persistante (sauf landing/describe_problem)
│       ├── LandingScreen.tsx          # Écran d'accueil / choix de rôle
│       ├── ClientHomeScreen.tsx       # Accueil client (recherche, catégories, CTA IA)
│       ├── DescribeProblemScreen.tsx  # Formulaire IA (texte/photo/vocal) → appelle /api/analyze-problem
│       ├── ArtisanProfileScreen.tsx   # Fiche détaillée d'un artisan
│       ├── ChatScreen.tsx             # Messagerie client↔artisan + devis
│       ├── ArtisanDashboardScreen.tsx # Tableau de bord artisan (revenus, demandes, devis)
│       ├── SearchScreen.tsx           # Recherche/filtre d'artisans
│       └── UserProfileScreen.tsx      # Profil utilisateur + moyens de paiement
├── tsconfig.json
└── vite.config.ts
```

Pas de dossier `tests/`, pas de fichier `*.test.*`/`*.spec.*`. Pas de dossier `.git` (le repo n'est pas encore initialisé).

### 1.2 Dépendances (`package.json`)

**Runtime**

| Paquet                 | Version   | Usage réel constaté                                                                                                                                                                  |
| ---------------------- | --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `react` / `react-dom`  | ^19.0.1   | Oui, cœur de l'app                                                                                                                                                                   |
| `vite`                 | ^6.2.3    | Oui, build + middleware dev dans `server.ts`                                                                                                                                         |
| `express`              | ^4.21.2   | Oui, serveur unique (`server.ts`)                                                                                                                                                    |
| `@google/genai`        | ^2.4.0    | Oui, dans `server.ts` uniquement (`GoogleGenAI`)                                                                                                                                     |
| `dotenv`               | ^17.2.3   | Oui, charge `.env` dans `server.ts`                                                                                                                                                  |
| `@tailwindcss/vite`    | ^4.1.14   | Oui (plugin Vite)                                                                                                                                                                    |
| `@vitejs/plugin-react` | ^5.0.4    | Oui (plugin Vite)                                                                                                                                                                    |
| `lucide-react`         | ^0.546.0  | **Non utilisé** — aucun import trouvé dans `src/`. Tous les écrans utilisent des `<span className="material-symbols-outlined">` (police Google), pas les composants React de lucide. |
| `motion`               | ^12.23.24 | **Non utilisé** — aucun import trouvé. Les animations sont faites en CSS/Tailwind (`animate-in`, `animate-pulse`, `animate-bounce`, transitions).                                    |

**Dev**
`@types/node`, `autoprefixer`, `esbuild`, `tailwindcss`, `tsx`, `typescript` ~5.8.2, `@types/express`.

⚠️ `bun.lock` existe mais fait **0 octet** : aucune installation n'a encore généré de lockfile cohérent, et `node_modules/` est absent. L'environnement n'a jamais été `npm install`é dans ce checkout.

### 1.3 Scripts npm

| Script  | Commande                                                                                              | Rôle                                                                               |
| ------- | ----------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `dev`   | `tsx server.ts`                                                                                       | Lance Express + middleware Vite en mode dev (HMR)                                  |
| `build` | `vite build && esbuild server.ts --bundle --platform=node --format=cjs ... --outfile=dist/server.cjs` | Build client (Vite) + bundle serveur (esbuild → CJS)                               |
| `start` | `node dist/server.cjs`                                                                                | Sert le build de production (fichiers statiques + API)                             |
| `clean` | `rm -rf dist server.js`                                                                               | Nettoyage (commande Unix — ne fonctionnera pas telle quelle sous PowerShell natif) |
| `lint`  | `tsc --noEmit`                                                                                        | Vérification de types uniquement, **pas d'ESLint/Prettier configuré**              |

### 1.4 Points d'entrée

- **Client** : `index.html` → `src/main.tsx` → `src/App.tsx`
- **Serveur** : `server.ts` (point d'entrée unique, sert à la fois l'API et le contenu Vite/statique)
- **API** : une seule route, `POST /api/analyze-problem`

---

## 2. Cartographie du code

### 2.1 Machine à états de navigation (`App.tsx`)

Pas de routeur (pas de React Router, pas d'URL synchronisée). Navigation 100% pilotée par un seul state `currentView: AppView` avec union de 8 valeurs littérales :

```
'landing' → 'client_home' → 'describe_problem' → 'artisan_profile' → 'chat'
                ↕                                        ↕
             'search'                              'artisan_dashboard'
                ↕
             'profile'
```

Aucune de ces vues n'a d'URL propre : rafraîchir la page (F5) ramène toujours à `'landing'`. Pas de deep-linking possible, pas de bouton "retour" navigateur cohérent avec l'état applicatif.

### 2.2 État global (`App.tsx`)

| State             | Type                                 | Rôle                                                               |
| ----------------- | ------------------------------------ | ------------------------------------------------------------------ |
| `currentView`     | `AppView`                            | Vue active                                                         |
| `userRole`        | `UserRole` (`'client' \| 'artisan'`) | Bascule l'UI entre espace client et espace pro                     |
| `artisans`        | `Artisan[]`                          | Initialisé depuis `INITIAL_ARTISANS` (mock), jamais persisté       |
| `selectedArtisan` | `Artisan`                            | Artisan actif pour profil/chat, initialisé à `INITIAL_ARTISANS[0]` |
| `jobRequests`     | `JobRequest[]`                       | Demandes visibles côté artisan, mutées en mémoire                  |
| `chatMessages`    | `ChatMessage[]`                      | Fil de discussion, muté en mémoire                                 |
| `location`        | `string`                             | Quartier sélectionné (`'Dakar Plateau'` par défaut)                |
| `searchQuery`     | `string`                             | Texte de recherche partagé avec `ClientHomeScreen`                 |

Tout est perdu au rafraîchissement (aucun `localStorage`/`sessionStorage`/backend de persistance).

### 2.3 Écrans et props reçues

| Écran                    | Props reçues                                                                             | Rôle                                                                                                                                 |
| ------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `Header`                 | `currentView, setCurrentView, userRole, setUserRole, location, setLocation, unreadCount` | Barre sup., sélecteur de quartier (mock, liste statique), bascule de rôle, badge notifications                                       |
| `BottomNav`              | `currentView, setCurrentView, userRole`                                                  | Nav basse contextuelle au rôle                                                                                                       |
| `LandingScreen`          | `setCurrentView, setUserRole`                                                            | Choix "Client" vs "Artisan", aucune auth                                                                                             |
| `ClientHomeScreen`       | `artisans, setCurrentView, setSelectedArtisan, searchQuery, setSearchQuery`              | Recherche + filtre catégories + carte CTA IA + liste artisans + bandeau "Premium" (factice, `alert()`)                               |
| `DescribeProblemScreen`  | `setCurrentView, setSelectedArtisan, artisans`                                           | Formulaire IA (texte, upload photo, "enregistrement vocal" simulé) → **seul écran connecté à une vraie API**                         |
| `ArtisanProfileScreen`   | `artisan, setCurrentView`                                                                | Fiche artisan : bio, stats, réalisations, avis, partage (clipboard réel), favoris (state local, non persisté)                        |
| `ChatScreen`             | `artisan, messages, setMessages, setCurrentView`                                         | Chat simulé (réponse artisan via `setTimeout`), carte de devis, bouton "Appeler" → `alert()`                                         |
| `ArtisanDashboardScreen` | `artisan, jobRequests, setJobRequests, setCurrentView`                                   | Dashboard revenus (barres codées en dur), liste demandes, modal de devis, toggle disponibilité                                       |
| `SearchScreen`           | `artisans, setCurrentView, setSelectedArtisan`                                           | Recherche + filtres (métier, note mini) sur `artisans` en mémoire                                                                    |
| `UserProfileScreen`      | `userRole, setUserRole, setCurrentView, location`                                        | Identité codée en dur ("Diandé Diallo"), choix moyen de paiement (state local, aucun appel réseau), déconnexion → retour `'landing'` |

### 2.4 Backend (`server.ts`)

Un seul fichier, une seule route `POST /api/analyze-problem` :

1. Valide `description` (string requise).
2. Si `GEMINI_API_KEY` est définie et différente du placeholder `"MY_GEMINI_API_KEY"` → appelle `gemini-2.5-flash` avec un prompt qui exige un JSON strict.
3. Extrait le JSON de la réponse via regex `/\{[\s\S]*\}/` puis `JSON.parse`.
4. En cas d'absence de clé, d'erreur API, ou d'échec de parsing → **fallback heuristique** basé sur des `includes()` de mots-clés français (plomberie/électricité/climatisation/menuiserie) avec prix codés en dur.
5. Sert soit le middleware Vite (dev), soit les fichiers statiques `dist/` (prod), avec fallback SPA (`res.sendFile(index.html)`).

---

## 3. Classification RÉEL / MOCK / MANQUANT

### ✅ RÉEL (fonctionnel)

- Rendu React 19 + navigation par state machine.
- Formulaire de description de problème → appel réseau réel vers `/api/analyze-problem`.
- Intégration Gemini 2.5 Flash côté serveur (**si** une clé API valide est fournie).
- Fallback heuristique côté serveur (fonctionne sans clé API).
- Filtres de recherche/catégorie côté client (sur données en mémoire).
- Upload de photo dans `DescribeProblemScreen` (via `URL.createObjectURL`, réellement affiché, mais jamais envoyé nulle part).
- Copie du lien de profil dans le presse-papiers (`navigator.clipboard`).
- `tsc --noEmit` comme unique garde-fou de type.

### 🟡 MOCK (données ou simulation)

- **Toutes** les données métier (`src/data/mockData.ts`) : 3 artisans, 3 demandes, 3 messages — figées, non issues d'une base de données.
- Chat : la réponse de l'artisan est un `setTimeout` codé en dur (texte fixe, délai 2s), pas un vrai interlocuteur ni websocket.
- "Enregistrement vocal" dans `DescribeProblemScreen` : timer factice de 10s qui ajoute un texte fixe à la description ; aucun accès micro réel malgré la permission déclarée dans `metadata.json`.
- Revenus/stats du dashboard artisan (`245 000 FCFA`, barres du graphique, `28` demandes acceptées, `95%` taux de réponse, `4.9/5`) : valeurs codées en dur dans le JSX, ne reflètent pas `jobRequests`.
- Sélecteur de quartier (`Header.tsx`) : liste statique de 6 quartiers, ne géolocalise rien.
- Bandeau "Optimisez vos interventions" (géolocalisation) et bouton "Téranga Premium" : `alert()` JS, aucune fonctionnalité réelle.
- Numéro de téléphone artisan dans le chat (`+221 77 000 00 00`) : codé en dur, identique pour tous.
- Identité utilisateur dans `UserProfileScreen` ("Diandé Diallo", initiales "DD") : codée en dur, ne dépend d'aucune session.
- `unreadCount` (badge notifications) : dérivé de `chatMessages.length > 0 ? 1 : 0`, purement arbitraire.
- Bascule de rôle client/artisan : change juste `userRole`, aucune vérification d'identité ni de compte artisan réel.

### 🔴 MANQUANT

- **Authentification / comptes utilisateurs** : aucun login, JWT, session, OAuth. `userRole` est un simple toggle UI accessible à tout le monde.
- **Persistance** : aucune base de données, aucun `localStorage`. Toutes les mutations d'état (`setArtisans`, `setJobRequests`, `setChatMessages`) sont perdues au rechargement.
- **Géolocalisation réelle** : `metadata.json` déclare la permission `geolocation`, mais aucun appel à `navigator.geolocation` n'existe dans le code.
- **Paiements** : Wave / Orange Money / carte bancaire affichés dans `UserProfileScreen` comme choix radio, mais aucune intégration de paiement (pas de SDK Wave/OM, pas de Stripe, pas d'endpoint serveur dédié).
- **Tests** : aucun framework de test installé (pas de Vitest/Jest/Playwright), aucun fichier de test.
- **Routing réel / deep-linking** : pas de React Router, pas d'historique d'URL — navigation "en mémoire" uniquement.
- **Upload de fichier vers un serveur** : la photo jointe dans `DescribeProblemScreen` reste locale au navigateur (`URL.createObjectURL`), jamais transmise à `/api/analyze-problem` ni à aucun stockage.
- **Vraie messagerie temps réel** : pas de WebSocket/SSE, tout est simulé côté client.
- **CI/CD, linting de style (ESLint/Prettier)** : absents.

---

## 4. Risques identifiés

### 4.1 URLs d'images `googleusercontent.com` temporaires

Toutes les images (avatars, couvertures, réalisations, hero de la landing page) pointent vers des URLs `https://lh3.googleusercontent.com/aida-public/...` ou `.../aida/...` générées par Google AI Studio / Gemini. **Ces URLs sont notoirement temporaires/signées et peuvent expirer sans préavis**, ce qui cassera silencieusement l'affichage de toutes les images de l'app (aucune image locale de fallback, aucun `onError` sur les balises `<img>`). Impact : élevé, sur la quasi-totalité des écrans (`mockData.ts`, `LandingScreen.tsx`, `DescribeProblemScreen.tsx`).

### 4.2 Icônes — deux systèmes coexistants

- `lucide-react` est déclaré en dépendance (`package.json`) mais **jamais importé**.
- Toutes les icônes utilisées dans le code sont en réalité des `<span className="material-symbols-outlined">nom_icone</span>`, dépendant du chargement de la police Google Fonts "Material Symbols Outlined" via `index.html` (lien externe, pas de fallback local).
- Risque : dépendance à un CDN externe (Google Fonts) pour l'affichage de **toutes** les icônes de l'app — en cas d'indisponibilité réseau/CDN ou de blocage (contenu bloqué, hors-ligne), les icônes disparaissent silencieusement. Par ailleurs `lucide-react` gonfle inutilement `node_modules`/le bundle potentiel sans aucun bénéfice.

### 4.3 Absence de validation du JSON renvoyé par Gemini

Dans `server.ts` (lignes ~50-56) :

```ts
const jsonMatch = text.match(/\{[\s\S]*\}/);
if (jsonMatch) {
  const parsed = JSON.parse(jsonMatch[0]);
  return res.json(parsed);
}
```

- Aucun schéma (pas de Zod/Ajv/validation manuelle) ne vérifie que `parsed` contient bien `trade`, `priceEstimate`, `recommendedCount`, `urgency`, `suggestedDevis.{title,labor,materials,total}`.
- Si Gemini renvoie un JSON valide mais incomplet ou de forme différente, l'objet est renvoyé tel quel au client ; le frontend (`DescribeProblemScreen.tsx`) applique bien des valeurs par défaut (`data.trade || ...`) mais **uniquement au premier niveau** — un `suggestedDevis` malformé (ex. `labor` en string, champ manquant) sera propagé tel quel et pourra casser `toLocaleString()` côté `ChatScreen`/UI si jamais réutilisé.
- `JSON.parse` peut lever une exception si le JSON extrait par la regex est invalide (ex. JSON tronqué) — elle est bien rattrapée par le `catch (aiErr)` englobant, donc pas de crash serveur, mais elle **avale silencieusement l'erreur** (`console.error` seulement) et bascule sur l'heuristique sans en informer le client ni faire de retry.
- Aucune limite de taille/timeout explicite sur l'appel à `ai.models.generateContent`.

### 4.4 Gestion des secrets / `.env`

- `.env.example` contient un placeholder `GEMINI_API_KEY="MY_GEMINI_API_KEY"` — correct comme template.
- `.gitignore` exclut bien `.env*` (avec exception `.env.example`) — bonne pratique déjà en place.
- **Cependant** : le projet n'est pas encore un dépôt git (`Is a git repository: false`), donc ce `.gitignore` n'a jamais été testé en pratique sur ce checkout.
- Aucun fichier `.env` ou `.env.local` n'existe actuellement → en l'état, le serveur tourne **toujours** en mode fallback heuristique (la condition `apiKey && apiKey !== "MY_GEMINI_API_KEY"` échoue faute de fichier `.env`).
- La clé API, si définie, n'est utilisée que côté serveur (`server.ts`) — c'est correct, elle n'est jamais exposée au client. Aucune fuite détectée dans le code source.
- `metadata.json` déclare `majorCapabilities: ["MAJOR_CAPABILITY_SERVER_SIDE_GEMINI_API"]`, cohérent avec l'architecture (clé API côté serveur uniquement).

### 4.5 Autres observations mineures

- `npm run clean` (`rm -rf dist server.js`) utilise une syntaxe Unix — échouera tel quel sous PowerShell natif (Windows) hors Git Bash/WSL.
- Le rôle `userRole` étant un simple state client sans vérification serveur, **n'importe quel visiteur peut s'auto-déclarer "artisan"** et accéder au dashboard pro (`ArtisanDashboardScreen`) — non exploitable aujourd'hui puisqu'il n'y a aucune donnée sensible réelle derrière, mais deviendra un vrai problème de sécurité dès qu'une authentification/backend réel sera branché s'il n'est pas revu à cette occasion.
- `bun.lock` vide + absence de `package-lock.json`/`node_modules` : l'environnement de ce checkout n'a jamais été installé (`npm install`/`bun install` à faire avant tout dev/build/test).

---

## 5. Proposition de plan en lots priorisés

_(à valider avant toute action — aucune modification n'a été faite)_

**Lot 0 — Remise en état de l'environnement (prérequis)**

- Initialiser le dépôt git (`git init`) si souhaité.
- `npm install` pour générer un vrai lockfile et `node_modules`.
- Créer un `.env.local` avec une vraie clé Gemini (ou documenter le mode fallback comme choix assumé).

**Lot 1 — Fiabilisation des assets (risque le plus visible/urgent)**

- Remplacer les URLs `googleusercontent.com` temporaires par des images hébergées durablement (assets locaux `/public` ou stockage type S3/Cloud Storage).
- Ajouter un fallback `onError` sur les `<img>` (image placeholder locale) en attendant.

**Lot 2 — Nettoyage des dépendances et icônes**

- Décider : soit migrer les icônes vers `lucide-react` (déjà en dépendance, évite la dépendance réseau à Google Fonts), soit retirer `lucide-react` et `motion` du `package.json` s'ils restent inutilisés.
- Auto-héberger la police "Material Symbols Outlined" si on garde ce système, pour ne plus dépendre du CDN Google Fonts en prod.

**Lot 3 — Robustesse de l'API `/api/analyze-problem`**

- Ajouter une validation de schéma (Zod) sur la réponse Gemini avant de la renvoyer au client.
- Ajouter un timeout explicite sur l'appel Gemini.
- Distinguer dans la réponse si le résultat vient de l'IA ou du fallback (utile pour debug/monitoring).

**Lot 4 — Fondations manquantes (plus gros chantier, à séquencer selon vos priorités produit)**

- Authentification réelle (comptes client/artisan) — condition préalable avant d'ouvrir `userRole` à autre chose qu'une démo.
- Persistance (base de données) pour artisans, demandes, messages, remplaçant `mockData.ts`.
- Routing réel (React Router) pour le deep-linking et le rafraîchissement de page.
- Intégration paiement (Wave/Orange Money) — actuellement pure UI sans backend.
- Mise en place de tests (Vitest pour les composants, tests d'intégration pour `/api/analyze-problem`).

---

**J'attends votre validation avant d'entreprendre l'un de ces lots.**
