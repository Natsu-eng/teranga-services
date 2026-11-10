import { Artisan, ArtisanStats } from '../types';

/*
 * Données fictives RÉSERVÉES AUX TESTS (ESLint interdit leur import depuis le
 * code de production). Les chemins d'images ci-dessous sont volontairement
 * fictifs : les photos de démonstration ont été retirées de public/ (elles
 * étaient servies en production sans y être utilisées). Les tests ne
 * chargent jamais ces fichiers ; ne pas les réintroduire.
 */

export const INITIAL_ARTISANS: Artisan[] = [
  {
    id: 'idrissa-diop',
    name: 'Idrissa Diop',
    trade: 'Plomberie',
    avatarUrl: '/images/idrissa-diop-avatar.jpg',
    coverUrl: '/images/atelier-plomberie-cover.jpg',
    verified: true,
    rating: 4.9,
    reviewCount: 120,
    distance: '1.2 km',
    priceBase: '15.000 CFA',
    priceNumber: 15000,
    tags: ['Plomberie', 'Chauffe-eau', 'Dépannage'],
    tradeCodes: ['plomberie'],
    bio: "Artisan passionné avec plus de 8 ans d'expérience dans la plomberie sanitaire et le dépannage d'urgence à Dakar. Travail soigné et garanti. Spécialisé dans les installations résidentielles haut de gamme et la maintenance préventive.",
    stats: {
      experience: '8 ans',
    },
    available: true,
    realisations: [
      {
        id: 'real-1',
        title: 'Soudure cuivre sanitaire',
        imageUrl: '/images/idrissa-diop-realisation-soudure-cuivre.jpg',
        altText: 'Soudure tuyauterie cuivre',
      },
      {
        id: 'real-2',
        title: 'Installation chauffe-eau solaire',
        imageUrl: '/images/idrissa-diop-realisation-chauffe-eau-solaire.jpg',
        altText: 'Chauffe-eau solaire toit',
      },
      {
        id: 'real-3',
        title: 'Rénovation salle de bain haut de gamme',
        imageUrl: '/images/idrissa-diop-realisation-salle-de-bain.jpg',
        altText: 'Salle de bain rénovée',
      },
    ],
    reviews: [
      {
        id: 'rev-1',
        author: 'Fatou K.',
        avatarInitials: 'FK',
        rating: 5,
        date: 'Il y a 2 jours',
        comment:
          '"Excellent travail, très ponctuel ! Idrissa a su réparer une fuite complexe en moins d\'une heure."',
      },
      {
        id: 'rev-2',
        author: 'Moussa S.',
        avatarInitials: 'MS',
        rating: 5,
        date: 'La semaine dernière',
        comment:
          '"Professionnel et honnête. Je recommande vivement pour tout ce qui touche à la plomberie sanitaire."',
      },
    ],
  },
  {
    id: 'maty-ndiaye',
    name: 'Maty Ndiaye',
    trade: 'Électricité',
    avatarUrl: '/images/maty-ndiaye-avatar.jpg',
    coverUrl: '/images/atelier-artisan-cover.jpg',
    verified: true,
    rating: 4.8,
    reviewCount: 85,
    distance: '2.5 km',
    priceBase: '20.000 CFA',
    priceNumber: 20000,
    tags: ['Électricité', 'Tableau électrique', 'Dépannage'],
    tradeCodes: ['electricite'],
    bio: "Électricienne diplômée avec 6 ans d'expérience. Installation complète, mise aux normes NFC 15-100 et dépannages d'urgence à Dakar.",
    stats: {
      experience: '6 ans',
    },
    available: true,
    realisations: [],
    reviews: [
      {
        id: 'rev-3',
        author: 'Awa D.',
        avatarInitials: 'AD',
        rating: 5,
        date: 'Il y a 3 jours',
        comment: '"Maty a remis à neuf tout notre tableau électrique. Très soigneuse."',
      },
    ],
  },
  {
    id: 'ousmane-fall',
    name: 'Ousmane Fall',
    trade: 'Climatisation',
    avatarUrl: '/images/atelier-artisan-cover.jpg',
    coverUrl: '/images/atelier-plomberie-cover.jpg',
    verified: true,
    rating: 4.9,
    reviewCount: 142,
    distance: '3.1 km',
    priceBase: '18.000 CFA',
    priceNumber: 18000,
    tags: ['Climatisation', 'Entretien', 'Recharge Gaz'],
    tradeCodes: ['climatisation'],
    bio: 'Spécialiste de la climatisation résidentielle et tertiaire. Nettoyage antibactérien, recharge de gaz R410/R32 et installation Inverter.',
    stats: {
      experience: '10 ans',
    },
    available: true,
    realisations: [],
    reviews: [],
  },
];

export const ARTISAN_STATS_BY_ID: Record<string, ArtisanStats> = {
  'idrissa-diop': {
    ratingAvg: 4.9,
    reviewCount: 28,
    interventionsCount: 28,
    responseRate: null,
    revenueFcfa: 245000,
  },
};
