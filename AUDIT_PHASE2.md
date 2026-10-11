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

## Mise à jour — `feat/artisan-dashboard` (Lot 12c)

Points ci-dessous traités depuis la mise à jour précédente (§3, §6) :

- **§3, point 1 (« le dashboard artisan n'existe pas »)** : corrigé plus
  avant que prévu. `/pro` était déjà passé d'un `ComingSoon` à
  `InterventionsScreen` nu (Lot 12b) ; il rend maintenant
  `ArtisanDashboardScreen` — toggle de disponibilité, stats réelles,
  demandes regroupées par statut.
- **§3, point 2 et §6 (BottomNav artisan)** : "Demandes" et "Revenus"
  pointaient tous deux vers `/pro`. Fusionnés en une seule entrée
  "Tableau de bord" — `/pro` étant désormais un écran unique qui réunit
  déjà les deux, deux liens distincts vers le même contenu n'auraient
  rien apporté.
- **§2/§4, `PATCH /artisans/me`** : n'existait pas ("hors périmètre Lot 9"
  dans le plan initial). Existe maintenant, strictement limité à
  `is_available` (rôle artisan, scopé à son propre profil résolu depuis
  le token) — l'édition complète du profil (bio, métiers, zone) reste un
  chantier distinct (onboarding artisan), non anticipé ici.
- **§6, `GET /artisans/{id}/stats` jamais consommé côté front** : corrigé.
  Le hook `useArtisanStats` était orphelin pour deux raisons cumulées, pas
  une seule : aucun écran ne l'appelait (vrai jusqu'à ce lot), **et**
  `httpApiClient` n'implémentait même pas `getArtisanStats` — l'appel
  serait de toute façon retombé silencieusement sur `mockApiClient` (données
  fictives : `monthlyRevenue`, `weeklyRevenues`...) via le mécanisme de
  fallback méthode-par-méthode d'`index.ts`. Le type `ArtisanStats` a été
  aligné sur le contrat réel du backend (`rating_avg`, `review_count`,
  `interventions_count`, `response_rate`, `revenue_fcfa`) et
  `httpApiClient.getArtisanStats` ajouté.
- **Cohérence des stats vérifiée** : `rating_avg`/`review_count` (dénormalisés,
  Lot 9), `interventions_count` (compte réel des `intervention.status =
  terminee`), et `revenue_fcfa` (somme des `payment.status = reussi` liés aux
  interventions de l'artisan) sont bien dérivés de données réelles, aucune
  n'est en dur. Nuance à garder en tête : `revenue_fcfa` vaudra 0 pour
  n'importe quel artisan tant que le Lot 14 (paiements) n'est pas construit,
  puisqu'aucun endpoint ne permet encore de créer un `payment` — ce n'est
  pas une valeur factice, juste une source de données encore vide par
  construction. `response_rate` reste `null` (déjà le cas avant ce lot,
  aucun champ `responded_at` n'existe dans le modèle pour le calculer).

---

## Mise à jour — `feat/auth-signup`

- **§1, écrans `/connexion`, `/connexion/code`** : le point d'audit implicite
  "`verify-otp` crée toujours un compte `client` sans notion d'inscription"
  est corrigé. Nouveau point d'entrée `/connexion` (`AuthEntryScreen` : Se
  connecter / Créer un compte) et `/connexion/role` (`RoleSelectScreen` :
  choix client/artisan, la carte artisan reprend déjà l'identité `bg-primary`
  de l'Espace Pro). `PhoneScreen` déplacé sur `/connexion/telephone`,
  `OtpScreen` inchangé côté route mais relaie désormais `intent`/`role`
  jusqu'à `verify-otp`. Nouvel écran `/bienvenue-artisan` (protégé) affiché
  une fois après une inscription artisan, avant `/pro`.
- **§2, `POST /auth/verify-otp`** : contrat étendu (`intent`, `role`),
  détail complet et arbitrage sécurité/UX (énumération) en
  BUILD_PLAN.md §4.3. `POST /auth/request-otp` explicitement inchangé.
- **§3, cohérence client/artisan** : un compte artisan a désormais un
  `artisan_profile` réel dès sa création (`is_available=false`,
  `verified_status=none`) au lieu de n'exister qu'après un premier login
  implicite non différencié — l'atterrissage sur `/bienvenue-artisan` puis
  `/pro` (Lot 12c) est cohérent immédiatement après l'inscription, sans état
  intermédiaire bricolé.
- **Sécurité** : `admin` n'a jamais été, et n'est toujours pas, attribuable
  via l'application — ce lot rend l'invariant explicite et testé
  (`app.services.auth._SIGNUP_ROLES`, tests `test_auth_signup.py`) plutôt que
  de compter implicitement sur l'absence d'UI admin (AUDIT_PHASE2.md §1,
  `role.ts:4-9`).
- **Reste hors périmètre** (inchangé par ce lot) : onboarding artisan (bio,
  métiers, zone, documents de vérification), messagerie, retrait d'Express,
  paiements.

## Mise à jour — `feat/artisan-onboarding`

- **§1, écrans `/pro` et `/pro/onboarding`** : le point d'audit implicite
  "un artisan fraîchement inscrit atterrit sur un dashboard vide et
  trompeur" est corrigé. `ArtisanWelcomeScreen` mène désormais directement à
  `/pro/onboarding` (nouvel écran : édition du profil, déclaration des
  métiers, upload des documents CNI/selfie, checklist de progression,
  bandeau de statut explicite). `ArtisanDashboardScreen` (`/pro`) a été
  basculé de `useArtisan` (vue publique) vers `useMyArtisanProfile` (vue de
  soi-même, expose `verifiedStatus`) : tant que l'artisan n'est pas
  `verified`, il affiche le même bandeau de statut + un CTA vers
  l'onboarding au lieu des cartes de stats à zéro et d'une liste de demandes
  toujours vide (qui ne peut d'ailleurs jamais se remplir avant
  vérification, `ARTISAN_NON_VERIFIE` verrouillé depuis le Lot 12). Les
  stats ne sont même plus interrogées (`GET /artisans/{id}/stats`) pour un
  artisan non vérifié -- appel réseau désormais évité, pas seulement caché.
- **§2, nouveaux endpoints backend** : `PATCH /artisans/me` étendu (bio,
  years_experience, base_location, avatar_url -- mise à jour partielle,
  `is_available` seul continue de fonctionner à l'identique, non-régression
  testée), `POST`/`DELETE /artisans/me/trades`, `POST`/`GET
  /artisans/me/documents` + `GET .../content`. Détail complet : BUILD_PLAN.md
  §3.2, §3.3.
- **§3, cohérence client/artisan** : l'écart "artisan_profile créé vide,
  aucun flux pour le remplir" (relevé au lot `feat/auth-signup`) est comblé.
  Un artisan peut désormais aller jusqu'au bout du cycle
  none -> pending -> (verified, une fois un futur Lot C admin construit) --
  sans jamais pouvoir se rendre visible en recherche publique ni recevoir de
  demande avant d'être réellement vérifié.
- **Sécurité (lot sensible, données d'identité)** : type de fichier validé
  par magic bytes (jamais extension/Content-Type déclarés, prouvé par test
  -- une extension falsifiée est rejetée), taille plafonnée, clé de
  stockage aléatoire jamais devinable, `doc_url` jamais une URL publique
  (prouvé par test), isolation stricte par propriétaire (un artisan ne
  peut ni lister ni lire les documents d'un autre -- 404, jamais de
  distinction observable), rate limité par utilisateur. Couche de stockage
  abstraite (`StorageBackend`) : dev en local hors du dépôt git et hors de
  tout répertoire servi statiquement ; un fournisseur cloud privé reste à
  brancher avant la prod (disque local non persistant sur Railway).
- **Décision produit actée** : un artisan non vérifié est **invisible** en
  recherche publique (`GET /artisans`), pas seulement non contactable --
  justification complète dans `app.services.artisans.list_artisans` et
  BUILD_PLAN.md §3.2. `GET /artisans/{id}` reste volontairement accessible
  quel que soit le statut, pour que l'artisan voie son propre profil.
- **Reste hors périmètre** (inchangé par ce lot) : revue admin des documents
  (approve/reject, Lot C -- `verification.status` reste à `pending` tant
  qu'aucun endpoint ne le fait évoluer), messagerie, retrait d'Express,
  paiements.
- **Mise à jour ultérieure (même branche, avant merge)** : l'avatar a
  finalement été implémenté en upload de fichier réel (`POST
  /artisans/me/avatar`, stockage public dédié distinct du stockage privé
  des documents, servi via `/static/avatars`) suite à un retour direct de
  l'utilisateur après la première livraison de ce lot -- le champ URL texte
  reste disponible en complément (coller un lien externe), les deux
  chemins écrivent le même champ `avatar_url`. Détail complet :
  BUILD_PLAN.md §3.3.

## Mise à jour — `feat/admin-verification`

- **§1, écran `/admin/verifications`** : ferme le trou identifié dans la
  mise à jour `feat/artisan-onboarding` ci-dessus ("revue admin ... hors
  périmètre, verification.status reste à pending indéfiniment"). Nouvel
  écran, volontairement en dehors de `MainLayout` (outil interne, pas
  d'identité "client"/"artisan Pro") : file d'attente FIFO, aperçu du
  document à la demande (`Blob` + `URL.createObjectURL`, jamais un `<img
  src>` direct qui ne pourrait pas porter l'en-tête `Authorization`),
  approbation en un clic, rejet avec motif obligatoire. `RequireAdminRoute`
  (nouveau, `src/components/auth/`) affiche l'écran 404 standard pour tout
  compte non-admin -- ni redirection vers `/connexion`, ni message "accès
  refusé", les deux auraient confirmé l'existence de la section.
- **§2, nouveaux endpoints backend** : `GET /admin/verifications`, `GET
  .../{id}/content`, `POST .../{id}/approve`, `POST .../{id}/reject`, `GET
  /admin/artisans/{id}` -- tous `require_role(Role.ADMIN)`. Détail complet :
  BUILD_PLAN.md §3.2, §4.4.
- **§3, cohérence client/artisan** : le cycle complet (upload artisan Lot B
  → décision admin Lot C → conséquence visible côté client) est maintenant
  bouclé et testé de bout en bout dans les deux sens : approbation complète
  → l'artisan apparaît en recherche publique ET devient contactable (`POST
  /interventions` accepte enfin) ; rejet → reste invisible et non
  contactable, avec motif consultable par l'artisan qui peut renvoyer un
  document (`pending -> rejected -> pending` après renvoi, testé).
- **Sécurité (lot sensible)** : le rôle admin reste, comme documenté au lot
  `feat/auth-signup` pour le rôle en général, **totalement inatteignable
  via l'application** -- ce lot l'illustre concrètement avec
  `scripts/create_admin.py`, seul chemin, exigeant un accès direct à la
  base. Toutes les routes `/admin/*` renvoient exactement les mêmes erreurs
  génériques (`403 ROLE_INSUFFISANT`, `401`) que n'importe quelle autre
  route protégée par rôle ailleurs dans l'API -- aucune fuite d'information
  distinctive pour un tiers non autorisé qui tenterait de deviner
  l'existence de l'espace admin. `reviewed_by`/`reviewed_at` sont posés
  côté serveur depuis l'admin authentifié (JWT), jamais un champ d'entrée
  accepté du client (testé en tentant de l'injecter explicitement dans le
  corps de la requête).
- **Reco documentée, non construite** : une table d'audit dédiée
  (journal append-only, au-delà de `reviewed_by`/`reviewed_at` qui ne
  portent qu'une seule décision par ligne `verification`) serait utile si
  l'espace admin grandit (plusieurs admins, besoin d'historique complet).
  Hors périmètre pour l'instant -- voir BUILD_PLAN.md §4.4 pour le
  raisonnement complet.
- **Reste hors périmètre** (inchangé par ce lot) : messagerie, retrait
  d'Express, paiements, écran admin listant l'historique
  approuvé/rejeté (l'API le permet déjà via `?status=`, pas encore
  d'onglet côté UI).

## Mise à jour — `fix/user-name-and-contact-privacy`

- **Diagnostic (corrige §5, ligne « il n'y a même pas de fuite à corriger »
  ci-dessus)** : cette conclusion était incomplète. Les schémas artisan
  publics n'exposent en effet aucun champ `phone`/`email` dédié, mais
  `user.full_name` était rempli avec le numéro de téléphone en guise de
  placeholder à l'inscription (`resolve_account_for_intent`,
  `app/services/auth.py`, Lot `feat/auth-signup` -- aucune saisie de nom
  n'existait avant ce lot). Le téléphone fuyait donc bien en public, via un
  champ qui n'avait pas l'air d'un champ de contact. La fiche artisan
  affichait littéralement le numéro à la place du nom.
- **Correction à la racine** : `full_name` est désormais requis au signup
  (`app/core/full_name.py`, 2-150 caractères) pour les deux rôles ; le
  placeholder `full_name=phone` est supprimé du code, pas seulement masqué.
  Édition après coup ajoutée -- absente jusqu'ici, y compris pour le rôle
  client qui n'avait aucun moyen d'éditer son propre nom : `PATCH /users/me`
  (nouveau, rôle-agnostique) et `full_name` accepté dans `PATCH /artisans/me`.
- **Défense en profondeur pour les comptes hérités** : les comptes créés
  avant ce lot portent encore potentiellement leur téléphone en `full_name`
  en base (aucune migration de données n'a été faite -- décision volontaire,
  voir plus bas). `app/services/identity.py::public_display_name` détecte à
  la volée (`looks_like_phone_number`) et masque ces cas derrière un repli
  neutre partagé ("Membre Téranga"), appliqué à chaque point de
  sérialisation publique identifié par grep systématique : `GET /artisans`,
  `/artisans/{id}`, `/artisans/{id}/reviews`, l'avis embarqué dans
  `InterventionOut` (ces deux derniers n'étaient pas explicitement cités
  dans la demande initiale mais partagent la même classe de vulnérabilité).
  Jamais appliqué en vue de soi (`/auth/me`, `UserOut`) ni côté admin, qui
  doivent voir la valeur réelle pour pouvoir la corriger/juger.
- **Verrou de non-régression** : `backend/tests/test_public_contact_privacy.py`
  simule un compte hérité (`full_name = phone`) et vérifie explicitement
  l'absence du numéro dans le texte de chaque réponse publique sérialisée
  (recherche, fiche détail, avis), plus un test de garde inverse confirmant
  qu'un vrai nom n'est jamais masqué par erreur.
- **Pas de migration de données pour les comptes existants** : décision
  volontaire -- le masquage applicatif couvre déjà tous les cas
  d'affichage public, et une migration de données one-shot n'aurait
  bénéficié qu'aux quelques comptes de test/dev créés avant ce lot (le seed
  `scripts/seed.py` construit ses `User` directement, hors
  `resolve_account_for_intent`, et avait donc déjà de vrais noms -- vérifié,
  aucun changement nécessaire). Un compte hérité concerné voit son propre
  placeholder en vue de soi (non masqué) et peut le corriger via `PATCH
  /users/me`/`PATCH /artisans/me`, désormais disponibles.
- Front : nouvel écran `/connexion/nom` (`NameScreen`) entre le choix du
  rôle et le téléphone, uniquement en signup (le login ne passe jamais par
  cet écran). Édition du nom ajoutée à l'onboarding artisan (section "Mon
  profil", juste après la photo) et au profil client (icône crayon inline
  à côté du nom affiché).
- **Reste hors périmètre** (exclu explicitement de ce lot) : avatar, photo
  de couverture -- lot séparé (traité par `feat/profile-media` ci-dessous).

## Mise à jour — `feat/profile-media`

- **Photo de couverture** : `POST /api/v1/artisans/me/cover`
  (`app/services/covers.py`), même régime PUBLIC que l'avatar (même
  stockage, magic bytes JPEG/PNG, taille `COVER_MAX_UPLOAD_BYTES`), et
  `cover_url` accepté dans `PATCH /artisans/me`. La colonne existait déjà
  (schéma initial) mais n'était alimentée par aucun endpoint.
- **Rate limiting des médias publics** : l'avatar n'en avait aucun (le
  BUILD_PLAN le justifiait par un risque moindre qu'un KYC). Ajouté sur les
  deux uploads avec un budget unique par utilisateur
  (`RATE_LIMIT_PROFILE_MEDIA_UPLOAD_PER_USER_*`, 20 / 10 min) : chaque
  envoi écrit un fichier sur disque, un compte authentifié pouvait donc
  remplir le stockage public sans limite.
- **Défaut corrigé — suppression du média d'un autre artisan** (préexistant
  sur l'avatar, reproduit tel quel par la première version de la
  couverture) : l'ancien fichier était effacé dès que son URL commençait
  par `/static/avatars/`. Or `avatar_url`/`cover_url` sont éditables à la
  main via `PATCH /artisans/me` : coller l'URL publique (donc connue) du
  média d'un autre artisan, puis uploader une photo, effaçait le fichier
  de cet autre artisan -- sa fiche publique affichait alors une image
  cassée. Même mécanisme entre les deux médias d'un même artisan (une
  couverture pouvait faire effacer l'avatar). Correction :
  `app/services/profile_media.py::owned_media_key` n'accepte qu'une clé au
  format exact généré, sous le répertoire du profil courant et du bon type.
  Verrouillé par `test_profile_media_ownership.py` (scénarios d'attaque
  explicites, traversée `..`, extension inattendue, URL externe).
- **Défaut corrigé — ordre suppression/commit** : l'ancien fichier était
  effacé avant le commit. Un commit raté laissait le profil pointer vers un
  fichier disparu. Le service renvoie désormais la clé obsolète
  (`MediaUploadResult`), la route ne l'efface qu'après le commit.
- **Validation des URL saisies à la main** : `avatar_url`/`cover_url` sont
  rendues dans un `<img src>` sur la fiche publique ; seul le http(s)
  absolu est accepté (`422` pour `javascript:`, `data:`, chemin relatif…),
  une chaîne vide ou de blancs est ramenée à `null` (retirer la photo).
- Front : bandeau de couverture dans l'onboarding artisan, avatar en
  chevauchement (même composition que `ArtisanProfileScreen`), état
  d'envoi et erreur distincts par photo, pré-contrôle local type/taille
  (`features/artisans/profileMedia.ts`) qui évite une requête et un envoi
  décompté du budget pour un fichier voué au refus. Inputs fichier passés
  de `hidden` à `sr-only` + `aria-label` : atteignables au clavier et
  nommés pour les lecteurs d'écran.
- **Dettes restantes, documentées** (✅ *toutes trois closes par
  `feat/media-hardening`, ci-dessous*) : le plafond de 4 Mo est dupliqué côté
  front (pré-contrôle seulement -- relever `COVER_MAX_UPLOAD_BYTES` sans
  toucher `PROFILE_MEDIA_MAX_BYTES` ferait refuser localement des fichiers
  que le serveur accepterait) ; le rate limiter reste en mémoire par
  processus (même dette que l'OTP) ; aucun redimensionnement/recompression
  serveur des images (une couverture de 4 Mo est servie telle quelle).

## Mise à jour — `feat/media-hardening`

- **Correctif préalable** : `ruff check` échouait sur `main` (ligne de 110
  caractères dans `profile_media.py`, produite par `ruff format` après le
  dernier `ruff check` du lot précédent). Corrigé en premier commit.
- **Rate limiting partagé et persistant.** L'état en mémoire par processus
  (OTP, triage IA, documents, photos) ne survivait ni à un redémarrage ni à
  plusieurs instances : derrière N workers, la limite réelle était
  multipliée par N, et chaque déploiement remettait tous les compteurs à
  zéro. Remplacé en staging/prod par `PostgresRateLimiter` (table
  `rate_limit_hit`, migration `b5e65b93246d`, réversible) :
  - chaque vérification tourne dans **sa propre transaction**, jamais celle
    de la requête — un appel refusé ensuite (fichier invalide, code faux)
    reste décompté, sinon échouer exprès suffirait à contourner la limite ;
  - **verrou consultatif par clé** : sonde à l'appui, sans lui 20 requêtes
    simultanées passaient toutes pour une limite de 5 ; avec lui, exactement
    5 (test `test_concurrent_checks_never_exceed_the_limit`) ;
  - **aucune clé en clair** : numéro, IP ou identifiant ne sont stockés que
    sous forme d'empreinte SHA-256 (vérifié en base après le test live :
    0 ligne en clair) ;
  - purge des lignes expirées, échec fermé si la base est indisponible ;
  - `RATE_LIMIT_BACKEND` : `memory` en dev, `postgres` par défaut ailleurs,
    `memory` **refusé au démarrage** hors dev.
- **Réencodage serveur des photos publiques** (Pillow 12.3,
  `app/services/image_processing.py`) : décodage complet (fichier polyglotte
  ou tronqué refusé, même avec une signature valide), plafond de pixels lu
  dans l'en-tête avant décodage (anti-bombe de décompression, garde-fou de
  Pillow conservé en seconde ligne), orientation appliquée puis **EXIF
  retiré, dont la position GPS** — jusqu'ici publiée telle quelle sur la
  fiche publique avec chaque photo prise au téléphone —, redimensionnement
  (512 / 1600 px), recompression JPEG q85 (PNG si transparence). Décodage
  JPEG réduit (`draft`) et hors boucle d'événements. Plafond d'envoi relevé
  de 4 à 10 Mo (une photo de téléphone dépasse souvent 4 Mo ; le poids servi
  ne dépend plus de l'envoi). Documents de vérification jamais retouchés.
- **Source unique des limites** : `GET /artisans/me/media-constraints`,
  dérivé des mêmes réglages que les routes d'upload (testé : un fichier d'un
  octet au-delà de la limite annoncée est refusé). Le front en tire
  pré-contrôle, `accept` et texte d'aide ; `PROFILE_MEDIA_MAX_BYTES`
  supprimé ; contraintes indisponibles = aucune limite devinée.
- **Vérification** : backend 453 tests + ruff + mypy, frontend `validate`
  vert ; test live via le proxy du front avec `RATE_LIMIT_BACKEND=postgres` :
  photo 3000×2000 avec GPS servie en 512×341 (avatar, 2 Ko) et 1600×1067
  (couverture, 15 Ko) sans GPS ni fabricant, bombe refusée (422), budget
  épuisé à la 21e tentative (429) et **toujours épuisé après redémarrage du
  backend**.

## Mise à jour — `chore/remove-express` (Lot 13)

- **§6, double implémentation de l'IA : close.** Diagnostic préalable
  (lecture seule) : `frontend/server.ts` portait quatre responsabilités —
  proxy de dev `/api/v1`, endpoint Gemini `POST /api/analyze-problem`, Vite
  en middleware, service statique + fallback SPA en production. Le seul
  appelant restant de `/api/analyze-problem` était `mock.ts` (jamais routé
  en production). Remplacements : proxy natif Vite (testé seul avant toute
  suppression), fallback SPA côté hébergeur (`vercel.json`), triage déjà
  migré (`POST /api/v1/ai/analyze`). Supprimés ensuite, preuve grep à
  l'appui : `server.ts`, `express`, `@types/express`,
  `http-proxy-middleware`, `@google/genai`, `dotenv`, `tsx`, `esbuild`,
  `GEMINI_API_KEY`, `APP_URL`, `metadata.json` et `DISABLE_HMR` (restes
  AI Studio), l'analyse legacy de `mock.ts`. Un seul jeu de configuration IA
  subsiste, côté backend (`MISTRAL_API_KEY` inchangée).
- **Fallback mock silencieux (constaté au Lot 12c, faux revenus artisan) :
  supprimé, pas seulement balisé.** `index.ts` exportait
  `{ ...mockApiClient, ...httpApiClient }` : toute méthode absente du client
  HTTP retombait sur des données fictives sans le signaler. Désormais
  `api = httpApiClient`, typé `ApiClient` complet — une méthode ajoutée au
  contrat sans implémentation HTTP ne compile plus. Les quatre méthodes
  encore servies par le seul mock (`listJobRequests`, `getChatMessages`,
  `sendChatMessage`, `getCurrentUser`) n'avaient aucun appelant (preuve
  grep) : retirées du contrat avec leurs données et types orphelins. Pour
  une fonctionnalité future sans backend : `notImplemented(feature)` lève
  une `ApiError` de code `not_implemented` au message affichable. `mock.ts`
  est réservé aux tests ; ESLint (`no-restricted-imports`, vérifié par une
  sonde) refuse tout import du mock ou de `mockData` depuis le code de
  production. Le bundle ne contient plus aucune donnée fictive (vérifié par
  grep sur `dist/`, 385 → 375 kB).
- **Dépendances** : `npm audit` passe de 16 vulnérabilités (1 critique) à
  0. Le retrait d'Express en élimine 7 (`proxy-addr`, `qs`, `braces`…) ;
  le reste est corrigé en patch dans les plages déclarées, dont
  `react-router` 7.18.1 → 7.18.4 (GHSA-qwww-vcr4-c8h2), seule dépendance
  vulnérable embarquée dans le bundle. npm 10.9.2 plantant dans
  `audit fix` (`edgesOut`), le lockfile a été résolu avec npm 11 puis
  vérifié par `npm ci` sous npm 10.
- **Production** : front 100 % statique ; `VITE_API_BASE_URL` (validée au
  chargement, testée) pour le déploiement multi-origines ; `vercel.json`
  ajoute des en-têtes de sécurité absents jusqu'ici (CSP, anti-clickjacking,
  `nosniff`, `Referrer-Policy`, `Permissions-Policy`), rejoués à
  l'identique par `vite preview`.
- **Vérification** : `npm run validate` vert après chaque commit ; build
  statique servi par `vite preview` (fallback SPA sur route profonde, en-têtes
  présents, une route API inconnue reste un 404 JSON et non `index.html`) ;
  parcours bout en bout **à travers le proxy Vite** (17/17) : front servi,
  fallback SPA, recherche, inscription artisan par OTP, `/auth/me`, triage
  IA, uploads avatar + couverture puis lecture publique, stats du dashboard,
  `/interventions/me`, rotation du refresh, rejeu refusé, logout.
- **Constaté pendant la vérification, hors périmètre** : la
  `MISTRAL_API_KEY` du `backend/.env` local est refusée par Mistral (401).
  Le triage retombe sur l'heuristique comme prévu (aucune erreur côté
  utilisateur) mais l'IA réelle n'est pas exercée tant que la clé n'est pas
  renouvelée.
- **Reste à vérifier au premier déploiement réel** : la CSP n'a été testée
  qu'en en-têtes HTTP (présence, valeurs), pas dans un navigateur réel en
  production. Points à surveiller dans la console : polices Google Fonts,
  images collées à la main (autorisées en `https:` uniquement), ouverture
  d'un PDF de vérification (URL `blob:`) côté admin.

## Mise à jour — `feat/design-refonte`

Refonte visuelle complète du front (direction « confiance chaleureuse »),
référence : [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md). Points de cet audit
concernés :

- **§1, contrôle d'accès des routes : close.** `ProtectedRoute` vérifie
  désormais le rôle (`roles`), aligné sur les `require_role` du backend :
  `/pro*` et `/bienvenue-artisan` -> artisan, `/mes-demandes` -> client,
  `/mes-interventions` -> client ou artisan. Un mauvais rôle voit un refus
  propre (`RoleRestricted`), jamais l'écran d'un autre rôle. L'espace admin
  reste derrière `RequireAdminRoute` (404 standard pour tout non-admin).
- **§3, « tout se ressemble » : close.** En-tête clair et navigation 4
  entrées côté client ; bandeau vert profond, navigation verte et or à 3
  entrées côté Pro ; profil scindé (client orienté besoins, artisan orienté
  activité, plus de moyens de paiement côté artisan). Vocabulaire séparé :
  « Devis et travaux » côté client, « Demandes reçues » côté Pro (le mot
  « interventions », terme d'artisan, n'est plus montré au client).
- **§6, filtrage en mémoire : close.** Accueil et recherche n'utilisent plus
  que les filtres serveur (`q`, `trade`, `min_rating`, `near`), état dans
  l'URL, saisie avec debounce.
- **§6, boutons factices : clos.** Retirés : « Téranga Premium »
  (`alert()`), « Voir les X avis » (`alert()`, remplacé par un vrai
  dépliage), « Voir tout » sans action, favori local jamais enregistré, cloche
  avec point rouge permanent (aucune notification réelle), choix de moyen de
  paiement enregistré nulle part (devenu informatif, « Bientôt »).
- **Constaté pendant le lot, corrigé** :
  - **mise en relation jamais branchée côté front** — cet audit marquait
    `POST /interventions` « consommé », à tort : aucun appel n'existait,
    « Demander un devis » menait à l'écran d'attente de la messagerie. La
    fiche artisan propose désormais les demandes ouvertes compatibles (métier
    exercé) puis crée la mise en relation ; sans demande, la demande IA
    `/demande?artisan=<id>` l'adresse directement à cet artisan ; « Mes
    demandes » propose « Choisir un artisan » pour une demande ouverte ;
  - `/demande` appelait l'IA (endpoint public limité) à chaque frappe :
    debounce 800 ms, 15 caractères minimum ; contenus simulés retirés
    (description et photo préremplies, faux message vocal qui ajoutait un
    texte inventé à la vraie demande) ; les 3 artisans affichés sont ceux du
    métier détecté ;
  - prix indicatif : `hourly_rate_fcfa` était déjà public mais ignoré
    (« Tarif sur devis » partout) -> « Dès X FCFA/h » ;
  - compte hérité dont le nom est resté le numéro : plus jamais affiché comme
    nom (salutation, avatar, profil) ;
  - `index.html` chargeait encore Google Fonts malgré la décision « zéro
    CDN » : polices auto-hébergées (`@fontsource-variable`), CSP
    `font-src 'self'`.
- **Vérification** : `npm run validate` vert après chaque commit (319 tests,
  contre 202 au départ), `npm run build` OK ; captures à 360 px (comptes du
  seed, client et artisan) sans défilement horizontal.
- **Reste hors périmètre** : messagerie (écran d'attente honnête), paiement
  en ligne, réalisations (aucune donnée côté backend), pagination « charger
  plus » de la recherche (première page seulement), revue visuelle de
  l'espace admin en conditions réelles (aucun compte admin local utilisé
  pour les captures).

## Mise à jour — `feat/messagerie`

Messagerie in-app client ↔ artisan, temps réel avec repli automatique,
référence : [BUILD_PLAN.md §3.4](BUILD_PLAN.md). Points de cet audit
concernés :

- **§1, `/messages/:conversationId` placeholder : close.** `ComingSoon`
  supprimé (preuve grep : plus aucun usage). `/messages` liste les
  discussions triées par activité, `/messages/:id` affiche le fil ; les deux
  routes exigent le rôle client ou artisan (l'admin en est exclu, côté front
  comme côté API).
- **§2, `GET|POST /conversations/{id}/messages` annoncés mais absents :
  clos.** Liste, détail, historique `since`/`before`, envoi texte et photo,
  lecture d'une photo, curseurs de lecture, compteur de non-lus, ticket et
  canal WebSocket (`app/api/v1/conversations.py`, `realtime.py`).
- **§4, tables `conversation`/`message` sans code : close.** Modèle complété
  (`seq`, curseurs de lecture, `last_message_at`, masquage, pièce jointe,
  contraintes), migration `c0a26cec109e` réversible (descente/remontée
  vérifiées, `alembic check` sans dérive), conversation ouverte avec chaque
  intervention.
- **§5, « déblocage de contact après engagement » : tranché.** Les
  coordonnées ne sont jamais débloquées : les échanges restent sur la
  plateforme et tout numéro ou e-mail écrit dans un message est masqué avant
  stockage, avec avertissement visible des deux parties (second étage de
  l'anti-désintermédiation, après l'absence de numéro sur les fiches).
- **Sécurité vérifiée par les tests** :
  - isolation : un tiers reçoit le même `403 CONVERSATION_ACCES_INTERDIT`
    qu'un fil inexistant, sur chaque route (lecture, envoi, photo, lecture
    d'une photo, marquage lu) ; le WebSocket ne publie qu'aux deux
    participants (test de diffusion avec un troisième compte connecté qui ne
    reçoit rien) ;
  - authentification WebSocket : sans ticket, ticket expiré, rejoué, falsifié,
    access token à la place d'un ticket, compte supprimé, admin → poignée de
    main refusée (`4401`) ; tests vérifiés par mutation (chaque contrôle
    retiré fait échouer au moins un test) ;
  - masquage : 18 formats de numéros sénégalais, numéros internationaux et
    liens `wa.me`, e-mails, plusieurs numéros dans un message, et 13 textes
    qui ne doivent PAS être masqués (montants, mesures, heures, dates) ;
  - photos : réencodées (EXIF/GPS absents du fichier stocké), stockage
    privé, `Cache-Control: private, no-store`, fichier supprimé si
    l'enregistrement échoue.
- **Fiabilité** : REST reste la source de vérité ; l'envoi ne dépend jamais
  du WebSocket (test front dédié, transport `unavailable`). Repli polling
  (5 s pour le fil, 30 s pour le badge) tant que le temps réel est
  indisponible, rattrapage `since` à chaque reconnexion et retour au premier
  plan, déduplication par identifiant (un message reçu à la fois par le
  temps réel et par REST n'apparaît qu'une fois).
- **Constaté pendant le lot, corrigé** :
  - `test_artisans_list_endpoint.py` dépendait du contenu de la base locale
    (seed) : désormais autonome (seed exécuté dans la transaction annulée du
    test) ;
  - tri par activité instable : `now()` renvoie l'heure de début de
    transaction (égalités) → `clock_timestamp()` ;
  - nom accessible du badge de navigation : annoncé « Messages, 3 non lus »
    (et non « , 3 non lus Messages »).
- **Vérification** : porte backend verte (`scripts/validate.py` : ruff,
  mypy strict, pytest), porte front verte (`npm run validate`, 371 tests,
  `npm run build`).
- **Dette ouverte (documentée, BUILD_PLAN.md §3.4)** : diffusion temps réel
  et registre des tickets en mémoire du processus, exacts en instance
  unique ; **bus Redis pub/sub obligatoire avant de passer à plusieurs
  instances backend**. Limites assumées du masquage : numéro épelé en
  lettres, découpé sur plusieurs messages ou visible sur une photo (périmètre
  de la détection NLP, Phase 3+).
- **Reste hors périmètre** : notifications push (application fermée),
  messages vocaux, suppression/édition d'un message, signalement d'un
  message à la modération.

## Mise à jour — `fix/localisation-demande`

Deux défauts d'ergonomie constatés en test manuel, et leur cause commune :
la localisation des demandes. **La protection géographique du serveur
n'est pas modifiée** : elle est seulement exposée en lecture.

- **Constat** : depuis la région parisienne, les demandes étaient
  localisées en France (GPS du navigateur lu **en silence** à l'envoi),
  alors que l'en-tête affichait « Dakar Plateau » — et l'en-tête n'avait
  aucune coordonnée (libellés seuls). Moussa (Plateau, 30 km) était à
  4 205 km : le serveur refusait l'envoi (`ARTISAN_HORS_ZONE`), à raison,
  mais **après** que le client avait choisi la demande.
- **Corrigé — lieu explicite** : quartiers de Dakar avec coordonnées
  réelles, liste unique partagée par l'en-tête et l'écran de demande (ils
  ne peuvent plus se contredire) ; « Intervention à : <lieu> » avant
  l'envoi ; la demande enregistre le lieu confirmé
  (`service_request.location_label` + coordonnées). Le GPS devient une
  suggestion : sur clic, résultat montré (coordonnées, distance à Dakar,
  avertissement hors région), appliqué après confirmation. La
  géolocalisation ne retombe plus jamais en silence sur le Plateau (même
  défaut corrigé dans l'onboarding artisan, qui l'utilisait aussi).
- **Corrigé — hors zone avant envoi** : `GET /requests/me/eligibility` et
  `GET /artisans/{id}/coverage`, lectures seules, appliquent la MÊME règle
  que `POST /interventions` (fonction unique). « Demander un devis »
  marque « Hors de sa zone » et rend la demande non sélectionnable ;
  l'écran de demande adressée à un artisan vérifie sa couverture du lieu
  avant l'envoi. « Mes demandes » montre le lieu et signale une demande
  hors de la région de Dakar (cas des demandes créées avant ce lot).
- **Protection serveur intacte** : un envoi hors zone reste refusé
  (`test_create_intervention_rejects_artisan_out_of_zone`, inchangé) ; un
  test vérifie que le marquage concorde toujours avec la décision.
- **Au passage** : la salutation disait toujours « Bonjour » ; elle suit
  désormais l'heure (« Bonsoir » de 18 h à 5 h).
- **Vérification** : porte backend verte, porte front verte, build OK.
- **Reste hors périmètre** : choix d'un point précis sur une carte (le
  quartier suffit aux rayons en kilomètres), adresse postale détaillée.

## Mise à jour — `feat/paiements`

Moteur de paiement complet, référence : [BUILD_PLAN.md §3.5](BUILD_PLAN.md).
Points de cet audit concernés :

- **§2, `POST /payments/init` et webhook annoncés mais absents : clos.**
  Initiation (montant toujours serveur), webhook signé et idempotent,
  consultation (client, artisan, admin), annulation, litige et arbitrage.
- **§4, tables `payment`/`platform_fee`/`payout` sans code : close.**
  Alimentées et contraintes en base (un paiement vivant, une commission, un
  versement par intervention ; cash sans fournisseur) ; `payment_event`
  remplace `wave_event_id` ; migration `b25862fcd340` réversible.
- **§5, paiement / anti-désintermédiation : livré.** Séquestre en ligne
  (le client est protégé, l'artisan payé à la confirmation), espèces
  enregistrées avec commission `due` (la fuite est mesurée), versement
  toujours vers le numéro vérifié du compte artisan.
- **Sécurité et fiabilité vérifiées par les tests** :
  - montant jamais pris du client (champ envoyé ignoré), commission sur le
    taux figé même après un changement de taux ;
  - webhook : signature forgée, autre secret, corps modifié, horodatage
    trop ancien -> 401 sans écriture ; rejeu -> `deja_traite`, un seul
    versement même rejoué après la complétion ; idempotence prouvée par
    mutation (deux défenses : event id unique, machine à états) ;
  - isolation financière : un tiers (client ou artisan) reçoit 403 sans
    aucun montant ; seul le client paie ; seul l'admin tranche ;
  - pannes du fournisseur : checkout -> 502 sans trace ; remboursement ->
    502, rien ne change ; versement -> complétion acceptée, versement
    `echoue` puis relancé une seule fois ;
  - paiement tardif d'une page abandonnée -> remboursé automatiquement.
- **Constaté pendant le lot, corrigé** :
  - **`.env.example` empêchait le démarrage** : `RATE_LIMIT_BACKEND=` (vide,
    « recommandé ») était rejeté par la configuration ; une valeur vide
    signifie désormais « choix automatique » (test : `.env.example` copié tel
    quel est une configuration valide) ;
  - le refus de l'artisan (`decline_reason`) ne savait pas décrire les
    autres clôtures : remplacé par `cancellation` (refus, annulation,
    arbitrage ; par qui ; motif), données existantes reprises ;
  - pendant un litige, rien n'empêchait le client de confirmer seul la fin
    des travaux (la transition `litige -> terminee` existe pour
    l'arbitrage) : la complétion exige désormais `en_cours` (trouvé par un
    test) ;
  - tuile « Revenus » du tableau de bord Pro ambiguë : « Chiffre
    d'affaires », montants payés avant commission.
- **Vérification** : porte backend verte (ruff, ruff format, mypy strict,
  pytest), porte front verte (`npm run validate`, `npm run build`).
- **Reste hors périmètre (documenté)** : agrégateur réel (point de bascule
  unique, §3.5), recouvrement des commissions dues en espèces,
  planification des relances de versement, libération automatique après
  délai, abonnement « Vérifié ».

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

- ✅ *Résolu au Lot 13 (`chore/remove-express`, voir la mise à jour dédiée en tête de document).* **Double implémentation de l'IA de triage.** `frontend/server.ts:42-149` contient encore l'ancien endpoint Express `POST /api/analyze-problem` (Gemini + fallback heuristique en dur), **mort en usage normal** (le front appelle `httpApiClient.analyzeProblem`, qui tape `/api/v1/ai/analyze`) mais toujours présent dans le code, toujours buildé, et toujours référencé par `mock.ts:145-179`. Deux fournisseurs IA différents coexistent dans le repo (Gemini côté Express legacy, Mistral côté FastAPI réel) avec deux jeux de variables d'env différents (`GEMINI_API_KEY` à la racine vs `AI_TRIAGE_PROVIDER`/`MISTRAL_API_KEY` dans `backend/.env.example`) — confusion probable pour quiconque configure l'environnement sans connaître l'historique. Ce nettoyage est le Lot 13 annoncé ("Retrait d'Express"), pas encore fait — cohérent avec le séquençage du plan, mais à garder en tête comme dette déjà identifiée et non une découverte.
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
