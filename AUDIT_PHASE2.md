# AUDIT PHASE 2 — Téranga Services

Date : 2026-07-25
Type : audit technique en lecture seule (aucun fichier du projet n'a été modifié, aucune branche créée, aucun commit).
Portée : état réel de l'application après le Lot 11 (triage IA migré), comparé au [BUILD_PLAN.md](BUILD_PLAN.md) (cible Phase 2) et à [AUDIT.md](AUDIT.md) (audit initial, Lot 0, pré-Phase 2).

---

## Mise à jour — `feat/requests-interventions` (première moitié du Lot 12)

Points ci-dessous traités depuis l'audit initial (non retouché ailleurs — ce
document reste la photographie du 2026-07-25, cette section note ce qui a
changé depuis) :

- **§1, route `/demande`** : le bug "ignore son résultat IA" (bouton final
  vers un artisan à id fixe `'idrissa-diop'`) est corrigé. `/demande` crée
  réellement une `service_request` (`POST /api/v1/requests`) avec le
  `trade_code` détecté par l'IA, et redirige vers `/recherche` filtrée
  **côté serveur** sur ce métier et la position (`GET /artisans?trade=&near=`).
- **§1, `useCurrentUser`/`artisanId`** : le placeholder `artisanId = user.id`
  est remplacé par le vrai `artisan_profile_id`, désormais exposé par
  `GET /auth/me` (`null` pour un client).
- **§2, endpoints backend** : `POST /requests`, `GET /requests/me`,
  `GET /requests/{id}`, `POST /interventions`, `GET /interventions/me`,
  `GET /interventions/{id}` existent maintenant et sont consommés (les trois
  premiers) ou prêts pour un futur dashboard artisan (les trois derniers,
  Lot 12 seconde moitié).
- **§4, écarts modèle de données** : `service_request` et `intervention` sont
  désormais exposés en écriture (avec `commission_rate_id` figé à la
  création) ; `quote`, `review` (écriture), `conversation`/`message` restent
  sans endpoint.
- **§7, synthèse priorisée** : l'item 1 ("Lot 12 — Entonnoir métier minimal")
  est démarré (sa première moitié). Item 3 ("Fermer le lien
  `user <-> artisan_profile`") est traité. Restent : dashboard artisan
  (`/pro`), devis/avis en écriture, messagerie, retrait d'Express, paiements.

## Mise à jour — `feat/quotes-reviews` (seconde moitié du Lot 12)

- **§1, `/pro`** : n'est plus un placeholder "Bientôt disponible". Premier
  vrai contenu de l'espace Artisan Pro (`InterventionsScreen`) : liste des
  interventions concernant l'artisan connecté (`GET /interventions/me`),
  actions réelles (accepter/refuser une mise en relation, poser un devis).
  Même écran réutilisé côté client sur la nouvelle route `/mes-interventions`
  (accepter/refuser un devis, confirmer la fin des travaux, déposer un avis).
- **§2, endpoints backend** : `POST /interventions/{id}/accept|decline`,
  `.../quote`, `.../quote/accept|refuse`, `.../complete`, `.../review`
  existent maintenant et sont tous consommés par le front.
- **§3, cohérence client/artisan** : l'espace artisan affiche désormais de
  vraies demandes reçues avec de vraies actions (accepter/refuser/deviser) —
  ce n'est plus une différence de seuls libellés de navigation entre les deux
  rôles, il y a un contenu et des actions réellement distincts.
- **§4, écarts modèle de données** : `quote` (création + transition) et
  `review` (écriture) sont désormais exposés et fonctionnels, avec
  recalcul réel de `rating_avg`/`review_count`. Seuls `conversation`/
  `message` (messagerie) restent sans endpoint.
- **§5, benchmark** : "Avis vérifiés liés à une intervention terminée" et
  "suivi de statut d'intervention" passent de *absent* à *implémenté* — la
  règle "intervention terminée" est vérifiée à la fois côté service (erreur
  normalisée) et par le trigger PostgreSQL (Lot 7).
- **§7, synthèse priorisée** : l'item 1 ("Lot 12 — Entonnoir métier minimal")
  est maintenant complet (les deux moitiés). Restent : messagerie, retrait
  d'Express, paiements — dans cet ordre de priorité décroissante, sauf
  réévaluation.

---

## Résumé exécutif

Le socle technique de la Phase 2 est solide et conforme au plan : FastAPI + PostgreSQL/PostGIS, 16 tables + `refresh_token` toutes modélisées et migrées, auth OTP + JWT avec rotation réelle, lecture des artisans géolocalisée, triage IA provider-agnostique. Le front a un vrai routeur (React Router 7), un vrai contexte d'auth, des états de chargement/erreur/vide gérés proprement.

Mais **le produit s'arrête à la phase de découverte**. Un client peut : atterrir, se connecter, chercher un artisan, voir un profil, décrire un problème à l'IA. Il ne peut **rien faire ensuite** : pas de demande persistée, pas de mise en relation, pas de devis, pas d'avis, pas de paiement, pas de messagerie — les trois routes qui matérialiseraient ça (`/messages/:id`, `/pro`, et l'écriture d'une demande) sont soit des placeholders "Bientôt disponible", soit absentes. C'est exactement pourquoi "tout se ressemble" entre client et artisan : **l'espace artisan n'existe tout simplement pas encore** (son dashboard est le même placeholder que la messagerie), donc il n'y a rien à différencier au-delà de deux barres de navigation avec des libellés différents.

Ce n'est pas une régression ni une dette cachée : c'est l'état exact annoncé par le BUILD_PLAN à ce stade (Lots 6-11 faits, Lot 12 — "Interventions, devis, avis" — pas commencé). Le reste de ce document détaille précisément où sont les coutures.

---

## 1. Inventaire des pages/routes front

Routeur : `frontend/src/App.tsx` (React Router 7, mode déclaratif `<Routes>/<Route>`, pas de convention fichier). Pas de `createBrowserRouter`, routes organisées sous 3 layouts (`MinimalLayout`, `NoBottomNavLayout`, `MainLayout`) + un catch-all.

| Route | Écran (fichier) | Auth | Rôle exigé | Données affichées | Source exacte |
|---|---|---|---|---|---|
| `/` | `LandingScreen.tsx` | Publique | — | Marketing statique : "250+ Artisans Pro" (L34), "Qualité 4.8/5" (L102), hero `/images/hero-plombier.jpg` | **Statique codé en dur**, aucun appel réseau |
| `/connexion` | `PhoneScreen.tsx` | Publique | — | Formulaire téléphone | **Backend réel** : `auth.requestOtp()` → `POST /api/v1/auth/request-otp` |
| `/connexion/code` | `OtpScreen.tsx` | Publique (accessible seulement via navigation depuis `/connexion`, redirige sinon) | — | Formulaire code OTP | **Backend réel** : `POST /api/v1/auth/verify-otp` |
| `/accueil` | `ClientHomeScreen.tsx` | Publique | — | Recherche, catégories, liste artisans recommandés | **Backend réel** : `GET /api/v1/artisans`, `GET /api/v1/trades`. Bandeau "Téranga Premium" (L228-246) : statique + `alert()` |
| `/recherche` | `SearchScreen.tsx` | Publique | — | Recherche/filtres artisans | **Backend réel** : mêmes endpoints qu'`/accueil` ; filtrage (texte, métier, note) fait **côté client en mémoire**, pas via les query params `ArtisanFilters` de l'API |
| `/demande` | `DescribeProblemScreen.tsx` | Publique | — | Formulaire IA + estimation + artisans recommandés | **Mixte** : `POST /api/v1/ai/analyze` (réel) + `GET /api/v1/artisans` (réel) pour la liste ; description et photo pré-remplies codées en dur (L15-20) ; "enregistrement vocal" simulé par `setInterval` (L41-63), aucun accès micro réel |
| `/artisans/:artisanId` | `ArtisanProfileScreen.tsx` | Publique | — | Profil détaillé, avis | **Backend réel** : `GET /api/v1/artisans/{id}` + `GET /api/v1/artisans/{id}/reviews`. Section "Réalisations" toujours vide (le mapping front force `realisations: []`, http-impl.ts:171, le backend n'expose pas cette donnée) ; bouton "Voir les X avis" → `alert()` codé en dur (L244) ; bouton "Voir tout" (réalisations, L187-189) sans `onClick` |
| `/messages/:conversationId` | `ComingSoon.tsx` | **Protégée** (`ProtectedRoute`, authentifié seulement) | Aucune vérif de rôle | Placeholder "La messagerie arrive bientôt" | **Aucune donnée**, texte de placeholder configurable par props |
| `/pro` | `ComingSoon.tsx` | **Protégée** (`ProtectedRoute`) | Aucune vérif de rôle (un client connecté peut y accéder aussi) | Placeholder "L'espace Artisan Pro arrive bientôt" | **Aucune donnée** — c'est le "dashboard artisan" annoncé, **il n'existe pas** |
| `/profil` | `UserProfileScreen.tsx` | **Protégée** | Aucune vérif de rôle | Identité, mode (client/artisan), moyens de paiement | **Mixte** : identité réelle via `useAuth()`/`GET /api/v1/auth/me` ; moyens de paiement (Wave/OM/Carte) = `useState` local, aucun appel réseau, aucune intégration de paiement |
| `*` (catch-all) | `NotFoundScreen.tsx` | Publique | — | 404 | Statique |

**Constat transversal sur l'auth des routes** : `ProtectedRoute.tsx` ne vérifie que "authentifié ou non" — jamais le rôle. Les 3 routes protégées (`/messages/:id`, `/pro`, `/profil`) sont donc accessibles à n'importe quel compte connecté, client ou artisan. La distinction n'existe que dans l'**affichage** (Header/BottomNav changent selon `toDisplayRole(auth.role)`), jamais dans le **contrôle d'accès**. Il n'y a aucune route ni écran admin (confirmé explicitement en commentaire, `role.ts:4-9` : *"there is no admin UI here"*).

**Bug de navigation confirmé** : `useCurrentUser.ts:34` fixe `artisanId: user.id` — un placeholder documenté en commentaire ("no user → artisan_profile link exposed by the backend yet"). Conséquence concrète : `UserProfileScreen.tsx:20` appelle `useArtisan(currentUser.artisanId)` pour afficher le nom de l'artisan connecté dans "Mode actuel" — mais `user.id` (table `user`) et `artisan_profile.id` sont deux UUID indépendants dans le modèle de données (BUILD_PLAN.md §2.2). Pour un vrai compte artisan (hors seed où les deux coïncident par hasard), cet appel interrogera un artisan_profile inexistant. Non testable en l'état car aucun endpoint n'expose le lien `user → artisan_profile.id`.

---

## 2. Inventaire des endpoints backend

Tous montés via `backend/app/api/v1/router.py` → `backend/app/main.py` (`include_router(v1_router, prefix="/api/v1")`). 5 routers, aucun orphelin.

| Endpoint | Auth | Consommé par le front ? |
|---|---|---|
| `GET /api/v1/health`, `/health/ready` | non | Non consommé par le front (probes infra) |
| `POST /api/v1/auth/request-otp` | non | **Oui** — `PhoneScreen.tsx` |
| `POST /api/v1/auth/verify-otp` | non | **Oui** — `OtpScreen.tsx` |
| `POST /api/v1/auth/refresh` | refresh token | **Oui** — `http.ts`, refresh silencieux sur 401 |
| `POST /api/v1/auth/logout` | refresh token | **Oui** — `AuthProvider.logout()` |
| `POST /api/v1/auth/logout-all` | JWT | **Non consommé** — aucun écran n'expose "déconnecter tous les appareils" |
| `GET /api/v1/auth/me` | JWT | **Oui** — restauration de session au montage, `useCurrentUser` |
| `GET /api/v1/artisans` | non | **Oui** — `ClientHomeScreen`, `SearchScreen`, `DescribeProblemScreen` |
| `GET /api/v1/artisans/{id}` | non | **Oui** — `ArtisanProfileScreen` |
| `GET /api/v1/artisans/{id}/reviews` | non | **Oui** — `ArtisanProfileScreen` |
| `GET /api/v1/artisans/{id}/stats` | optionnelle (revenus si owner/admin) | **Construit, non consommé** — le hook `useArtisanStats.ts` existe mais n'est appelé par **aucun écran monté** ; c'est littéralement le endpoint qui alimenterait un futur dashboard artisan |
| `GET /api/v1/trades` | non | **Oui** — catégories, mapping des métiers |
| `POST /api/v1/ai/analyze` | non (public, rate-limité) | **Oui** — `DescribeProblemScreen` |

### Endpoints annoncés au BUILD_PLAN mais absents du code (aucun fichier router)
`POST /api/v1/requests`, `GET /api/v1/requests/me`, `POST /api/v1/interventions`, `POST /api/v1/interventions/{id}/quote`, `POST /api/v1/interventions/{id}/quote/accept`, `POST /api/v1/interventions/{id}/complete`, `POST /api/v1/interventions/{id}/review`, `POST /api/v1/payments/init`, `POST /api/v1/webhooks/wave`, `GET|POST /api/v1/conversations/{id}/messages`, et un `PATCH /api/v1/artisans/me` explicitement noté "hors périmètre Lot 9" dans le plan.

### Écrans qui auraient besoin d'un endpoint qui n'existe pas
- **Écriture d'une demande** (fin de `/demande`) → a besoin de `POST /requests`. Aujourd'hui, le bouton "Voir les artisans" (`DescribeProblemScreen.tsx:250-256`) ne persiste rien : il pioche un artisan par id fixe (`'idrissa-diop'`, ligne 253) ou le premier de la liste, **indépendamment du résultat de l'IA**.
- **`/messages/:id`** → a besoin de `GET/POST /conversations/{id}/messages` (et probablement `POST /interventions` en amont pour qu'une conversation ait un sens).
- **`/pro`** (dashboard artisan) → a besoin au minimum de `GET /artisans/{id}/stats` (déjà prêt côté backend, jamais branché côté front) + `GET /requests` côté artisan (n'existe pas) + `/interventions` pour les demandes en cours.
- **Devis/accept/complete/review** → aucun écran actuel ne les appellerait de toute façon, ces parcours n'existent pas encore côté front.

---

## 3. Cohérence client / artisan — analyse honnête

Le signalement "tout se ressemble" est **factuellement exact**, et voici précisément pourquoi :

1. **Le dashboard artisan n'existe pas.** `/pro` rend le même composant générique `ComingSoon.tsx` que `/messages/:id`. Il n'y a littéralement aucun écran différent à comparer — pas une question de design, une question d'absence.
2. **La seule différenciation réelle aujourd'hui est dans `Header`/`BottomNav`** (`toDisplayRole(auth.role)`) :
   - Header : logo "Téranga Pro" au lieu du sélecteur de quartier + salutation.
   - BottomNav : "Demandes"/"Revenus" au lieu de "Accueil"/"Recherche".
   - Mais **"Demandes" et "Revenus" pointent tous les deux vers `/pro`** (`BottomNav.tsx:25` et `:37`) — deux entrées de nav distinctes pour une même page vide, ce qui est en soi une incohérence perceptible.
3. **`UserProfileScreen` est presque identique pour les deux rôles** : seul le sous-titre "Mode actuel" change de texte (L58-65) ; les moyens de paiement, la déconnexion, tout le reste est rigoureusement le même écran pour un client et un artisan.
4. **Aucun profil artisan enrichi** (édition bio, tarifs, disponibilité, métiers) n'existe côté front — `PATCH /artisans/me` n'est même pas prévu avant un lot ultérieur.
5. **Aucune notion de "mes demandes en cours" vs "mes clients"** — logique, puisque `service_request`/`intervention` n'ont aucun endpoint.

**Ce qui manquerait pour une vraie différenciation** (à mettre en regard de la synthèse §7) :
- Un vrai écran `/pro` : liste des demandes reçues (nécessite `service_request`/`intervention` exposés côté artisan), toggle disponibilité (`artisan_profile.is_available`, champ déjà en base, pas de `PATCH`), stats réelles (`GET /artisans/{id}/stats`, déjà prêt côté API, juste pas branché).
- Un écran de gestion de profil artisan distinct de `UserProfileScreen` (bio, métiers/`artisan_trade`, zone d'intervention, statut de vérification affiché — `verified_status` est calculé côté backend mais jamais montré à l'artisan lui-même sur son propre profil).
- Une navigation qui ne fasse pas pointer deux items vers le même placeholder.

---

## 4. Écarts avec BUILD_PLAN.md — modèle de données

Les 16 tables métier + `refresh_token` existent **toutes** en modèle SQLAlchemy et migration Alembic (chaîne `dcb3bd1b0258` → `285a1b35bc05`, `backend/migrations/versions/`). Aucune dérive modèle/DB détectée. La couverture API, en revanche, s'arrête net après `artisans`/`trades`/`ai`/`auth` :

| Table | En base | Exposée par un endpoint |
|---|---|---|
| `trade` | oui | oui (lecture) |
| `user` | oui | oui (lecture/écriture via `auth`) |
| `artisan_profile` | oui | lecture seule (pas de `PATCH /artisans/me`) |
| `verification` | oui | **non** — aucun endpoint, consommée uniquement en interne (`compute_verified_status`) |
| `artisan_trade` | oui | lecture indirecte seulement (imbriquée dans les réponses artisan), pas de CRUD dédié |
| `service_request` | oui | **non** — pas de `POST /requests` ni `GET /requests/me` |
| `intervention` | oui | **non** |
| `quote` | oui | **non** |
| `commission_rate` | oui | non exposée directement (référencée en interne) |
| `payment` | oui | **non** |
| `platform_fee` | oui | **non** |
| `payout` | oui | **non** |
| `review` | oui | lecture seule (pas d'écriture côté client) |
| `conversation` | oui | **non** |
| `message` | oui | **non** |
| `otp_code` | oui | écriture indirecte (`auth`) |
| `refresh_token` | oui | écriture indirecte (`auth`) |

**Parcours métier majeurs absents** : l'intégralité de l'entonnoir "demande → mise en relation → devis → intervention → paiement → avis" — c'est-à-dire le cœur commercial du produit (Lot 12, pas commencé). Rien dans ce constat n'est une surprise : c'est exactement la portée du Lot 12 telle que déjà actée dans le plan (§6).

---

## 5. Fonctionnalités du benchmark — implémentées / absentes / partielles

| Fonctionnalité actée | État |
|---|---|
| Vérification d'identité artisan avec badge | **Partielle.** Modèle `verification` + logique de dérivation `verified_status` entièrement implémentés côté backend (Lot 9), badge "Vérifié" affiché côté front (`ArtisanProfileScreen.tsx:117-122`, `ClientHomeScreen.tsx:174-179`). Manque : aucun flux de **soumission** de documents par l'artisan, aucun écran admin de **revue** des vérifications (`reviewed_by`/`reviewed_at` existent en base sans aucune UI). |
| Avis vérifiés liés à une intervention terminée | **Partielle.** Lecture des avis publiés fonctionne (`GET /artisans/{id}/reviews`). La règle métier "un avis n'existe que si `intervention.status = terminee`" est documentée au plan mais **aucun endpoint d'écriture** n'existe pour la tester en pratique — impossible de créer un avis aujourd'hui par l'app. |
| Suivi de statut d'intervention | **Absent.** Aucun endpoint, aucun écran ; `intervention.status` existe en base, jamais lu ni écrit par l'API. |
| Re-réservation | **Absent.** Suppose un historique d'interventions terminées, inexistant côté API. |
| Déblocage de contact après engagement | **Absent, mais la contrainte est déjà respectée par construction** : les schémas artisan backend n'exposent aucun champ téléphone/email (commentaire explicite `http-impl.ts:7-9`), donc il n'y a même pas de fuite à corriger — juste rien à débloquer, puisque rien n'est encore bloqué derrière un engagement (pas de messagerie active). |
| Paiements Wave/OM/cash | **UI seule, aucun backend.** `UserProfileScreen` affiche 3 boutons radio (Wave/OM/Carte) en `useState` local, zéro appel réseau. Modèle `payment` (avec `channel` incluant `cash`, `wave_event_id` pour l'idempotence) entièrement prêt en base, endpoint `POST /payments/init` absent. |
| Commission figée (`commission_rate` versionnée) | **Modélisée, jamais appliquée.** Table et logique de versionnement en base ; comme `intervention` n'existe pas côté API, aucune commission n'est jamais réellement figée en pratique. |

---

## 6. Dettes et incohérences visibles

- **Double implémentation de l'IA de triage.** `frontend/server.ts:42-149` contient encore l'ancien endpoint Express `POST /api/analyze-problem` (Gemini + fallback heuristique en dur), **mort en usage normal** (le front appelle `httpApiClient.analyzeProblem`, qui tape `/api/v1/ai/analyze`) mais toujours présent dans le code, toujours buildé, et toujours référencé par `mock.ts:145-179`. Deux fournisseurs IA différents coexistent dans le repo (Gemini côté Express legacy, Mistral côté FastAPI réel) avec deux jeux de variables d'env différents (`GEMINI_API_KEY` à la racine vs `AI_TRIAGE_PROVIDER`/`MISTRAL_API_KEY` dans `backend/.env.example`) — confusion probable pour quiconque configure l'environnement sans connaître l'historique. Ce nettoyage est le Lot 13 annoncé ("Retrait d'Express"), pas encore fait — cohérent avec le séquençage du plan, mais à garder en tête comme dette déjà identifiée et non une découverte.
- **BottomNav artisan incohérente** : "Demandes" et "Revenus" sont deux liens distincts qui pointent tous les deux vers `/pro` (le même placeholder) — `BottomNav.tsx:25` et `:37`.
- **`artisanId: user.id` en dur** (`useCurrentUser.ts:34`) : placeholder documenté en commentaire mais fragile — dès qu'un vrai compte artisan sera créé avec un `artisan_profile.id` distinct de `user.id`, `UserProfileScreen` et le lien "Messages" casseront silencieusement (404 sur `useArtisan`).
- **`DescribeProblemScreen` ignore son propre résultat IA** : le bouton final choisit un artisan par id fixe (`'idrissa-diop'`) ou le premier de la liste (L253), sans rapport avec le `trade_code` détecté par l'IA — le "matching" affiché à l'utilisateur est cosmétique.
- **Filtrage côté client au lieu de l'API** : `SearchScreen` et `ClientHomeScreen` récupèrent tous les artisans puis filtrent en mémoire (texte/métier/note), alors que `GET /artisans` supporte déjà `trade`, `q`, `min_rating`, `near`, `sort` côté serveur — la pagination réelle du backend n'est donc jamais exercée par ces écrans (ils consomment implicitement toujours la première page).
- **Boutons factices résiduels** : "Téranga Premium" (`ClientHomeScreen.tsx:236-241`) et "Voir les X avis" (`ArtisanProfileScreen.tsx:244`) déclenchent un `alert()` JS plutôt qu'une vraie action — hérité tel quel de l'audit initial (AUDIT.md §3, non retouché depuis).
- **Bouton "Voir tout" sans handler** : section Réalisations, `ArtisanProfileScreen.tsx:187-189`, aucun `onClick` — et de toute façon `realisations` est toujours un tableau vide (le backend n'expose pas cette donnée), donc la section entière ne rend jamais rien de visible en usage réel.
- **`GET /artisans/{id}/stats` construit et testé côté backend, jamais appelé côté front** en dehors d'un hook (`useArtisanStats.ts`) qui n'est branché à aucun écran monté — travail backend "en attente" du dashboard artisan qui le consommerait.
- **`POST /auth/logout-all` non exposé** dans l'UI (pas de "déconnecter tous les appareils" dans `UserProfileScreen`).
- **Pas de retour arrière cassé constaté** : `DescribeProblemScreen` utilise `navigate(-1)`, `ArtisanProfileScreen` un lien explicite `to="/accueil"`, `ProtectedRoute` restaure la page demandée via `state.from` après connexion — le flux de navigation est cohérent, contrairement à l'app pré-Phase 2 (AUDIT.md notait l'absence totale de routing réel — corrigé).
- **États vides gérés proprement** : `EmptyState`/`ErrorState`/`Skeleton` sont utilisés systématiquement sur les écrans branchés au backend (`ClientHomeScreen`, `SearchScreen`, `ArtisanProfileScreen`, `UserProfileScreen`, `DescribeProblemScreen`) — pas de dette ici, c'est un vrai progrès depuis l'audit initial.
- **Images** : `SafeImage` avec fallback local (`/images/placeholder-*.svg`) remplace les URLs `googleusercontent.com` temporaires signalées comme risque critique dans AUDIT.md §4.1 — ce risque semble corrigé (images servies depuis `/images/` local), mais ce point n'a pas été vérifié exhaustivement (pas d'inventaire complet des assets `/public/images` dans cet audit).

---

## 7. Synthèse priorisée — proposition de séquence (à valider, non exécutée)

Du plus structurant au moins urgent :

1. **Lot 12 — Entonnoir métier minimal (`service_request` → `intervention` → `quote` → `review`).** C'est le blocage racine : sans lui, aucun écran artisan différencié n'a de données à afficher, la messagerie n'a pas de contexte, les avis ne peuvent pas être testés, et le signalement "tout se ressemble" ne peut pas être résolu — il n'y a littéralement rien à différencier tant que l'artisan n'a pas de "demandes reçues" réelles à traiter. C'est le lot qui débloque tous les autres.
2. **Dashboard artisan réel sur `/pro`** (peut se faire en parallèle de la fin du Lot 12 ou juste après) : brancher `GET /artisans/{id}/stats` (déjà prêt, jamais consommé), lister les demandes/interventions issues du Lot 12, exposer le toggle `is_available`. C'est le levier le plus direct pour répondre au retour utilisateur.
3. **Fermer le lien `user ↔ artisan_profile`** côté API (exposer `artisan_profile_id` dans `UserOut` ou `/auth/me`) avant que le placeholder `artisanId: user.id` ne devienne un bug silencieux en production avec de vrais comptes artisan.
4. **Messagerie minimale** (`/conversations/{id}/messages`) une fois qu'il existe une `intervention`/`service_request` à laquelle l'attacher — sans quoi la route reste un `ComingSoon` légitime.
5. **Écriture des avis + affichage du statut de vérification à l'artisan lui-même** (aujourd'hui `verified_status` n'est visible que dans la fiche publique, jamais sur le propre profil de l'artisan connecté).
6. **Lot 13 — Retrait d'Express** : petit chantier isolé, aucune dépendance produit, mais élimine une source de confusion (deux fournisseurs IA, deux jeux de variables d'env) — faisable à tout moment sans attendre le Lot 12.
7. **Paiements (Lot 14)** : n'a de sens qu'une fois une `intervention` réelle existe à payer — à séquencer après le Lot 12, pas avant, quel que soit l'attrait de "montrer du Wave qui marche".
8. **Petits nettoyages UI** (bouton "Voir tout" sans handler, doublon "Demandes"/"Revenus" dans BottomNav, `alert()` résiduels "Premium"/"Voir les avis") : cosmétique, à regrouper avec les écrans qu'ils touchent plutôt qu'un lot dédié.

---

*Aucune modification n'a été apportée au projet pendant cet audit. J'attends votre validation avant d'entreprendre l'un de ces lots.*
