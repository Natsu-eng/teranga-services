import { Artisan, JobRequest, ChatMessage, ArtisanStats, CurrentUser } from '../types';

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
    location: 'Dakar, Sénégal',
    priceBase: '15.000 CFA',
    priceNumber: 15000,
    tags: ['Plomberie', 'Chauffe-eau', 'Dépannage'],
    bio: "Artisan passionné avec plus de 8 ans d'expérience dans la plomberie sanitaire et le dépannage d'urgence à Dakar. Travail soigné et garanti. Spécialisé dans les installations résidentielles haut de gamme et la maintenance préventive.",
    stats: {
      chantiers: '150+',
      responseTime: '< 1h',
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
    location: 'Dakar, Sénégal',
    priceBase: '20.000 CFA',
    priceNumber: 20000,
    tags: ['Électricité', 'Tableau électrique', 'Dépannage'],
    bio: "Électricienne diplômée avec 6 ans d'expérience. Installation complète, mise aux normes NFC 15-100 et dépannages d'urgence à Dakar.",
    stats: {
      chantiers: '95+',
      responseTime: '< 45 min',
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
    location: 'Dakar, Sénégal',
    priceBase: '18.000 CFA',
    priceNumber: 18000,
    tags: ['Climatisation', 'Entretien', 'Recharge Gaz'],
    bio: 'Spécialiste de la climatisation résidentielle et tertiaire. Nettoyage antibactérien, recharge de gaz R410/R32 et installation Inverter.',
    stats: {
      chantiers: '210+',
      responseTime: '< 30 min',
      experience: '10 ans',
    },
    available: true,
    realisations: [],
    reviews: [],
  },
];

export const INITIAL_JOB_REQUESTS: JobRequest[] = [
  {
    id: 'req-1',
    clientName: 'Moussa F.',
    clientAvatar: '/images/client-moussa-f-avatar.jpg',
    title: 'Fuite robinet cuisine',
    trade: 'Plomberie',
    location: 'Ouakam, Dakar',
    timeAgo: 'Il y a 5 min',
    estimatedPrice: '8 000 – 15 000 FCFA',
    status: 'new',
    description:
      "Le robinet sous l'évier fuit fortement depuis ce matin. Besoin d'intervention rapide.",
  },
  {
    id: 'req-2',
    clientName: 'Fatou D.',
    clientAvatar: '/images/client-fatou-d-avatar.jpg',
    title: 'Installation chauffe-eau',
    trade: 'Plomberie',
    location: 'Almadies, Dakar',
    timeAgo: 'Il y a 12 min',
    estimatedPrice: '25 000 – 40 000 FCFA',
    status: 'new',
    description: 'Pose d un chauffe-eau électrique 50L neuf dans la salle de bain principale.',
  },
  {
    id: 'req-3',
    clientName: 'Ousmane T.',
    clientAvatar: '/images/client-ousmane-t-avatar.jpg',
    title: 'Réparation canalisation',
    trade: 'Plomberie',
    location: 'Plateau, Dakar',
    timeAgo: 'Il y a 1h',
    estimatedPrice: '15 000 – 30 000 FCFA',
    status: 'new',
    description: "Engorgement au niveau de l'évacuation générale du sous-sol.",
  },
];

export const INITIAL_CHAT_MESSAGES: ChatMessage[] = [
  {
    id: 'msg-1',
    sender: 'artisan',
    text: "Bonjour, j'ai bien reçu votre photo. C'est une fuite standard au niveau du siphon.",
    timestamp: '10:45',
  },
  {
    id: 'msg-2',
    sender: 'artisan',
    timestamp: '10:46',
    devis: {
      id: 'devis-101',
      title: "Réparation de fuite d'évier",
      laborPrice: 8000,
      materialsPrice: 4000,
      totalPrice: 12000,
      currency: 'FCFA',
      status: 'pending',
      date: "Aujourd'hui",
    },
  },
  {
    id: 'msg-3',
    sender: 'client',
    text: "Merci Idrissa, c'est parfait pour moi. Je valide le montant.",
    timestamp: '10:48',
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

export const CURRENT_USER: CurrentUser = {
  id: 'user-diande-diallo',
  name: 'Diandé Diallo',
  initials: 'DD',
  verified: true,
  artisanId: 'idrissa-diop',
};
