# DESIGN_SYSTEM — Téranga Services

> Référence de toute interface du front (`frontend/`). Direction validée :
> **« confiance chaleureuse »** — fond chaud et clair, beaucoup d'air, serif
> accueillant pour les titres, et un badge **Vérifié** fort, signal de
> confiance central. Lot `feat/design-refonte`.
>
> Règle d'or : **un écran se construit avec les briques de
> `src/components/ui/` et les tokens de `src/index.css`**. Pas de hex en dur,
> pas de police externe, pas de style « bricolé » par surcharge de classes.

---

## 1. Principes

1. **La confiance d'abord.** Le badge Vérifié n'apparaît que pour un statut
   réellement vérifié côté serveur, et toujours sous la même forme.
2. **L'artisan est le héros de sa carte.** Photo ou initiales, nom, badge,
   note, distance, prix : lisibles d'un coup d'œil.
3. **Honnêteté.** Aucun chiffre inventé, aucune fonctionnalité simulée. Ce
   qui n'existe pas encore est dit (« Bientôt »), jamais imité.
4. **Deux espaces, un système.** Client et Pro partagent les mêmes
   composants ; l'espace Pro se signe par son bandeau vert profond (§6).
5. **Accessible par construction.** Les briques portent déjà libellés,
   focus, rôles ARIA et contrastes AA ; les écrans n'ont qu'à les utiliser.
6. **Mobile d'abord.** Tout est conçu et vérifié à 360 px, sans défilement
   horizontal.

---

## 2. Palette (tokens `@theme`, `src/index.css`)

Les classes Tailwind dérivent des tokens : `bg-primary`, `text-accent`,
`ring-border`, etc. **Aucun hex dans les composants.**

### Marque

| Token | Valeur | Usage |
|---|---|---|
| `primary` | `#004129` | Vert profond : titres, bandeau Pro, carte résultat IA, texte sur or |
| `primary-emerald` | `#0e5a3c` | Émeraude : badge Vérifié, bouton `brand`, focus, indicateurs |
| `primary-emerald-foreground` | `#8acfa9` | Texte secondaire sur vert profond |
| `accent` | `#e8a73b` | **Or, en accent seulement** : étoiles, CTA principal, détails Pro |
| `accent-alt` | `#feba4d` | Or plus clair : survol du CTA or |
| `accent-soft` | `#ffddb1` | Fond doux « attention / nouveau » |
| `accent-foreground` | `#815600` | Sur-titres or sur fond clair |
| `accent-foreground-strong` | `#291800` | Texte sur `accent-soft` |
| `accent-alt-foreground` | `#714b00` | (historique, conservé) |

> L'or n'est **jamais** un remplissage dominant : un seul CTA or par écran,
> des étoiles, des pastilles de détail.

### Surfaces et texte

| Token | Valeur | Usage |
|---|---|---|
| `background` | `#fcf9f8` | Fond chaud de l'app |
| `background-alt` | `#faf7f2` | Variante de fond (historique) |
| `surface` *(ajout)* | `#ffffff` | Cartes, champs, barres |
| `emerald-tint` *(ajout)* | `#e8f3ec` | Surface douce : zones IA, encarts d'info, pastilles « info » |
| `emerald-tint-strong` *(ajout)* | `#d2e8da` | Survol / bord discret sur `emerald-tint` |
| `surface-muted` | `#f6f3f2` | Blocs internes neutres |
| `foreground` | `#1c1b1b` | Texte principal |
| `muted-foreground` | `#404943` | Texte secondaire (contraste > 7:1) |
| `muted-foreground-soft` | `#707972` | Placeholders, contour des champs (4,6:1) |
| `border`, `border-subtle`, `border-strong`, `border-faint` | — | Séparateurs fins uniquement (pas de bordure de carte) |

### États

| Token | Usage |
|---|---|
| `destructive` / `destructive-soft` | Erreurs, refus, actions destructives |
| `success` / `success-foreground` | Pastilles « terminé / validé » |
| `brand-wave`, `brand-orange-money` | Pastilles des moyens de paiement uniquement |

Les 25 tokens d'origine sont inchangés ; les ajouts sont marqués et
commentés dans `index.css`. **Ajouter un token** : le déclarer dans
`@theme` avec un commentaire d'usage, puis le documenter ici. Renommer ou
supprimer un token exige une preuve grep d'absence d'usage.

---

## 3. Typographie

Polices **auto-hébergées** (`@fontsource-variable/*`, importées dans
`src/main.tsx`, servies depuis `/assets`). **Aucun CDN** : la CSP impose
`font-src 'self'`.

| Famille | Classe | Rôle |
|---|---|---|
| **Fraunces** (variante opsz : graisse + taille optique) | `font-display` | Titres, salutations, noms de section, noms d'artisans, chiffres clés |
| **Figtree** (variante graisse) | `font-sans` (défaut du `body`) | Corps de texte et interface |

Chaque pile se termine par un repli système réel (`ui-serif, Georgia…` /
`system-ui, -apple-system, 'Segoe UI'…`).

### Échelle

| Classe | Taille | Usage |
|---|---|---|
| `text-display-xl` | 36 px | Accroche marketing (landing, grand écran) |
| `text-display-lg` | 30 px | Titre d'écran d'auth, accroche |
| `text-display-md` | 24 px | Titre de page, nom sur la fiche |
| `text-display-sm` | 20 px | Titre de section, AppBar, salutation |
| `text-title` | 17 px | Titre de carte (nom d'artisan, métier) |
| `text-base` / `text-sm` | 16 / 14 px | Corps |
| `text-caption` | 11 px | Sur-titres en capitales, libellés de navigation |

Les `display-*` embarquent leur interlignage et leur approche (tokens).

---

## 4. Forme, profondeur, mouvement

| Token | Valeur | Usage |
|---|---|---|
| `rounded-card` | 20 px | **Toutes** les cartes |
| `rounded-field` | 14 px | Champs, blocs internes d'une carte |
| `rounded-sheet` | 28 px | Bas arrondi des bandeaux, panneaux modaux |
| `rounded-full` | — | Boutons, pastilles |
| `shadow-card` | diffuse, teintée émeraude | Carte au repos (**jamais de bordure dure**) |
| `shadow-card-hover` | plus marquée | Carte interactive survolée, panneaux |
| `shadow-bar` | vers le haut | Barres fixées en bas |
| `shadow-cta` | halo or | Sous le bouton `primary` |

- **Focus** : contour émeraude de 2 px sur tout élément interactif
  (`:focus-visible`, couche base). Sur fond vert profond, poser
  `data-tone="dark"` sur le conteneur : le contour passe à l'or.
- **Mouvement** : transitions courtes (150–200 ms). `prefers-reduced-motion`
  neutralise globalement animations et transitions ; les déplacements
  décoratifs utilisent `motion-safe:`.
- **Encoche** : `pb-safe` pour toute barre fixée en bas.

---

## 5. Composants (`src/components/ui/`)

| Composant | Usage | À savoir |
|---|---|---|
| `Button` / `ButtonLink` | Toute action / navigation habillée en bouton | Variantes `primary` (or, **1 par écran**), `brand` (émeraude), `outline`, `ghost`, `danger`, `danger-outline`, `danger-ghost`, `on-dark` ; tailles `sm` / `md` / `lg` ; `isLoading` (désactive + `aria-busy`) ; `type="button"` par défaut |
| `IconButton` | Bouton icône seule | `label` obligatoire (nom accessible) ; tonalités `light`, `on-dark`, `danger`, `brand` (action principale pleine, ex. « Envoyer » de la messagerie) |
| `Card` | Toute surface de contenu | `tone` `default` / `tint` / `dark`, `padding`, `interactive`, `as` ; pour une carte-lien, habiller un `<Link>` avec `cardClasses()` |
| `VerifiedBadge` | Le signal de confiance | Pastille émeraude pleine, texte blanc, bouclier-check ; `sm` (cartes), `md`, `lg` (fiche) ; uniquement si `verified` |
| `Avatar` | Personne | Photo via `SafeImage` (lazy) sinon initiales colorées déterministes ; nom resté au numéro → silhouette ; `decorative` quand le nom est écrit à côté |
| `Chip` / `ChipLink` | Filtre (métier, note) | `aria-pressed` ; `ChipLink` pour une pastille qui navigue |
| `Rating`, `StarRow`, `RatingInput` | Notes | « Nouveau » sans avis (jamais « 0,0 »), format « 4,8 » ; saisie par boutons nommés |
| `StatTile` | Indicateur chiffré | Valeur Fraunces + libellé capitales ; `on-dark` sur bandeau ; valeur **courte** (le détail va dans `hint`) |
| `SectionHeader` | Titre de page / section | Niveau `as` indépendant de la taille ; `eyebrow`, `description`, `action` |
| `AppBar` | En-tête de sous-page | Retour robuste (`useBackNavigation` : page précédente de l'app, sinon `backTo`) ; `tone="pro"` dans l'espace Pro |
| `TextField`, `TextAreaField`, `SelectField` | Formulaires | Libellé toujours associé (`hideLabel` le masque visuellement seulement), `hint` et `error` reliés par `aria-describedby`, erreur annoncée |
| `StatusPill` | État (demande, intervention, document) | Tonalités `neutral`, `info`, `success`, `warning`, `danger` ; le texte porte le sens |
| `Switch` | On / off | `role="switch"` ; `tone="on-dark"` sur le bandeau Pro |
| `Sheet` | Panneau modal | `role="dialog"`, focus piégé puis restitué, Échap, voile ; contenu monté à l'ouverture |
| `EmptyState`, `ErrorState`, `Skeleton`, `Spinner` / `PageLoader` | États | Chaque écran branché gère chargement (squelette à la forme du contenu), erreur (avec « Réessayer ») et vide (avec une suite) |
| `Logo` | Marque | Typographique ; `variant="pro"`, `tone="on-dark"` |
| `SafeImage` | Toute image | Repli local si l'URL casse ; `loading="lazy"` par défaut (`eager` pour un héros) |

Composants métier partagés : `ArtisanCard` (accueil, recherche, résultats
IA — identique partout), `InterventionCard` (client et artisan),
`QuoteRequestSheet`, `VerificationStatusBanner`, `IdentityCard`.

Paiements (`src/features/payments/`) : `MoneyBreakdown` (les montants
selon la partie — client : « Total à payer » et « aucun frais ajouté » ;
artisan : prix, commission avec son taux, « Vous recevez »), `PaymentPanel`
(volet « Paiement » de la carte d'intervention : pastille d'état, montants,
explication datée, action payer/reprendre). Choix d'un moyen de paiement
ou de versement : cartes-radio (`fieldset`/`legend`, `input type="radio"`)
comme `QuoteRequestSheet`, jamais une liste déroulante.

Messagerie (`src/features/messages/components/`) : `MessageBubble` (mes
messages à droite sur fond `primary-emerald`, ceux de l'autre à gauche sur
surface claire, heure discrète), `PendingBubble` (message
optimiste : « Envoi… », puis en échec la raison avec « Réessayer » /
« Supprimer »), `MaskedNotice` (avertissement de masquage), `AttachmentImage`
(photo chargée avec authentification, jamais par URL publique),
`MessageComposer` (champ multiligne, photo, `IconButton tone="brand"`).

### Règle des classes

`cn()` assemble des classes **sans fusion Tailwind** (pas de
`tailwind-merge` : nos tokens `text-display-*` seraient confondus avec des
couleurs). Conséquence : **`className` sert à la mise en page** (marges,
largeur, `flex-1`, placement). Une couleur, un fond ou un padding différent
→ une **variante** du composant, jamais une surcharge (le résultat
dépendrait de l'ordre du CSS généré).

---

## 6. Client, Pro, Admin : règles de différenciation

| | Client (et visiteur) | Pro (artisan) | Admin |
|---|---|---|---|
| En-tête | **Clair** : quartier + « Bonjour, Prénom » en Fraunces, avatar ou « Se connecter » | **Bandeau vert profond** : logo Téranga **Pro** (or), avatar | **Clair et neutre** : logo + mention « Admin » |
| Navigation basse | 4 entrées (Accueil, Recherche, Messages, Profil), surface blanche, indicateur vert clair | 3 entrées (Tableau de bord, Messages, Profil), **fond vert profond, indicateur or** | Aucune (outil interne) : **navigation à huit onglets sous l'en-tête** (Vue d'ensemble, Vérifications, Artisans, Utilisateurs, Avis, Litiges, Commissions, Journal), défilement horizontal sur mobile, `aria-current` sur la section courante |
| Héros d'écran | Fond chaud, beaucoup d'air | Le bandeau se **prolonge** dans le héros (`rounded-b-sheet`), indicateurs qui le chevauchent | — |
| AppBar de sous-page | `tone="light"` | `tone="pro"` | — |
| Profil | Orienté **besoins** : nouvelle demande, mes demandes, devis et travaux | Orienté **activité** : vérification, tableau de bord, profil Pro, fiche publique | — |

- **Vocabulaire** : chaque espace parle sa langue. Côté client, la mise en
  relation et son suivi s'appellent « **Devis et travaux** » (jamais
  « interventions », terme d'artisan) ; côté Pro, « **Demandes reçues** ».
  La route reste `/mes-interventions` (URL technique, inchangée).
- L'habillage dépend **toujours** du rôle renvoyé par le serveur
  (`auth.role`), jamais d'un choix de l'utilisateur.
- **Contrôle d'accès** : `ProtectedRoute roles={[...]}` refuse proprement un
  rôle non autorisé (`RoleRestricted`, avec une sortie vers son propre
  accueil). L'espace admin passe **uniquement** par `RequireAdminRoute` :
  un non-admin voit la 404 standard, aucun indice de l'existence de
  l'espace.
- **Back-office, garde-fous visibles** : toute action admin sensible passe
  par une feuille de confirmation (`ConfirmActionSheet`) qui **énonce
  l'effet exact avant d'agir** (ex. « ses interventions en cours
  continuent »), exige le motif quand le serveur l'exige (bouton inactif
  tant qu'il est trop court) et affiche le refus serveur en clair (« dernier
  administrateur »…). Ce qui n'est pas permis n'est pas proposé, et la
  raison est écrite sur la ligne (`guard`) : jamais un bouton qui échoue.
  Rien ne se supprime : on masque, on suspend, on ajoute un taux — et le
  journal est en lecture seule. Côté Pro, une suspension est annoncée par
  un bandeau avec son motif, un avis signalé ou masqué porte son statut.
- **Anti-désintermédiation** : aucun numéro de téléphone d'artisan n'est
  affiché nulle part ; le contact passe par « Message » et « Demander un
  devis ». Un nom resté au numéro (compte hérité) n'est jamais affiché comme
  un nom (`lib/identity.ts`).
- **Argent, transparence d'abord** : jamais un montant sans dire ce qu'il
  est. Le client lit « Total à payer » (le prix du devis, sans frais
  ajoutés) et sait que la commission de Téranga, nommée avec son taux, est
  prise sur la part de l'artisan ; l'artisan lit le prix, la commission
  (montant et taux figé, « estimée » tant qu'elle n'est pas enregistrée) et
  « Vous recevez ». Chaque état de paiement a une phrase qui dit ce qui se
  passe et quand (séquestre, versement, remboursement), formulée pour la
  partie qui lit. Les espèces sont proposées avec leur conséquence (« sans
  protection du séquestre »). Aucun montant n'est calculé par le front.
  **Lancement espèces seulement** (paiement en ligne coupé) : on ne promet
  rien qui n'existe pas — ni séquestre, ni « payer en ligne » ; le volet
  invite à « Déclarer le paiement en espèces » et l'écran l'explique.
- **Messagerie, transparence d'abord** : la liste rappelle que numéros et
  e-mails sont masqués automatiquement et que les photos ne sont visibles
  que des deux participants ; un message masqué le dit aux deux parties
  (jamais de masquage silencieux). Connexion temps réel perdue : une ligne
  discrète (`role="status"`, « quelques secondes de délai »), jamais une
  alerte — l'envoi continue de fonctionner. Badge de non-lus : pastille or
  sur l'icône « Messages » des deux navigations, nombre exact annoncé dans
  le nom du lien (« Messages, 3 non lus »).

---

## 7. Accessibilité (AA) — liste de contrôle

- Contrastes : texte ≥ 4,5:1 (vérifiés : blanc sur émeraude 8,2:1, vert
  profond sur or 5,6:1, `muted-foreground` > 7:1) ; contour des champs ≥ 3:1.
- Tout élément interactif a un nom accessible et un focus visible.
- Chaque champ a un `<label>` (éventuellement `sr-only`), jamais un
  placeholder seul.
- Erreurs : `role="alert"` ; résultats asynchrones : `aria-live` ;
  chargements : `aria-busy`.
- États exposés par ARIA (`aria-pressed`, `aria-checked`, `aria-current`,
  `aria-expanded`), jamais par la seule couleur.
- Champs fichier : `sr-only` + libellé, jamais `hidden` (inatteignable au
  clavier).
- Lien d'évitement « Aller au contenu » dans la coque principale.

---

## 8. À ne pas faire

- Un hex, une `rgba()` ou une taille arbitraire (`text-[11px]`) dans un
  composant → utiliser / créer un token.
- Charger une police, une icône ou un script depuis un CDN.
- Une bordure dure autour d'une carte.
- Plus d'un bouton or par écran ; de l'or en grand aplat.
- Afficher une donnée inventée (note, volume, prix) ou simuler une
  fonctionnalité (bouton `alert()`, choix enregistré nulle part, faux
  enregistrement vocal).
- Filtrer en mémoire ce que l'API sait filtrer (`q`, `trade`,
  `min_rating`, `near`).
