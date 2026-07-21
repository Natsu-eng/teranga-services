import { Artisan, JobRequest, ChatMessage } from '../types';

export const INITIAL_ARTISANS: Artisan[] = [
  {
    id: 'idrissa-diop',
    name: 'Idrissa Diop',
    trade: 'Plomberie',
    avatarUrl:
      'https://lh3.googleusercontent.com/aida/AP1WRLtk-9VpiU0kRd16VlFxRrCPKGJeU5QgCl8X_KLPQq-IzkmQLAUv_mokRkM8JFS1QY39xBpwkgVvsTZ0Z-qLXbxFTBEHFLT88BSNZb9CS0s7u43QllVSShT0XAm23mHf3RDceQ_oAzSq2yLON-jj1vTElaVkxnLbWfV1RFGWb1FyM4JcYh6PFQugeVy897akZ4On-Q7G5eAwPHDXzcDpJWW1iBCXT0rBVZe5L0aBiieLxdxr4oTEh-dWdPc',
    coverUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuDCBiAi1cOp54U5Wv8LsSxDS6MwnGMHeSYGNyHYOH2bHdyMdyTrPEbGgq2sCdzPAPXLZ8vaVtxJLIN6E90rFc9o9aqxd8zQjRtNDLsQFUL1jjTa7Mt88cRbkaEdST5VFyKy6Dd4GQ07eOaxz0tY0pFNH_blb8dOhTaWJf6qqk9CzfJ--P7hwMUk3WsIlNGKQXpVnGaFLg8GTiPyp8dp7QCrM_R-MLL5x70HdEs0_5oXm5WnJ2-x-lfsOCBEu3wupvgCWF-UR8kPm0us',
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
        imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDia7XgUEnr8x-uVy_0JiDxW4ZifAQqL6OjRhR-yo2vTNBjmZh7G3NlRjZ0R2ipAb6Gi42edM6Cop7Om1TmDvXsxIw7sVRvzDf8yCPvblAbdV10GusRm-KQ2dbv1-RA_4gn85CuYSgTa9hZbppUMdYan4wWM7Vwr1AUH62lMnFI2haL9lonTKqifKOmU-ysf4Olw9L1AQJnyr-AQcOPQb2KKu5zyrLnT_b9BKT4ZZqCQAXBFzW_Tcrnkg_Rm-cX3phD4GgB3QSu8gr7',
        altText: 'Soudure tuyauterie cuivre',
      },
      {
        id: 'real-2',
        title: 'Installation chauffe-eau solaire',
        imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuDAAijPf-xr9qhXDYuGF_7JmUHh_ms7qs_7vaJEO-0HV6uBSzKcvw3BYyrKuxdOa5VpxuWCCN4JruO8CuZ7w25UU9BQ8xiDIFKX3BSjDqPJbE81GjVGNkDNBtx9bKCQDHaRA0Af5cjLR0B0_No3spWGw0MHRYiRTDAKnr44qtnkfZgBt5dYyxlpP5QG5qNiK2zlqXzb7ip21JojCLvdTgdEhcb0Aa0fHfwSP_ADsXSSrrvG5T58zQTzvGo-LQbSN0s1H7kZFk-UfMx1',
        altText: 'Chauffe-eau solaire toit',
      },
      {
        id: 'real-3',
        title: 'Rénovation salle de bain haut de gamme',
        imageUrl:
          'https://lh3.googleusercontent.com/aida-public/AB6AXuBQ-9kZapJaJLorNvMdrJPcEBBESN_kr8ARKvtFTkxG2hNEuFw71T0cdsJamLWxUu8DGrUXS3SRjZSutVDr40z67-WCs83SRcXeK-wFHk0A5qne8m30lQi9W3iUENHY5Z4JU3aCOXtZgIBtWfwMb4kf1KmunggpnBKTKUGr7mHvNlWSEBI_U4uNLokkCTPz3u2aE-c6HG2_8VYj_fctUVgqwJfLMxo_OrcIOCq1i2WXb-mosbSji1vb3tl58CLRY4pUpH67JbhObMB5',
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
    avatarUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuBxaLo1Ucscw2Y1MZAQQqC88LC-rjLe1fqFsOXFd9Q8o1qHBbTfxc83d5Z-xg-YXTQy-nXqgebI-DmzFe1prZnex4CPdINZAMn9whOTOjXcnR9iVNKidlsEHfYhW3A8kLlLEsuvIq3uJKfCeScyBI6T0e-hUMBbjuFYi0UqJDcqwxWQUgtATucYghhyA2-V8C_L5QwpnA5ooJkOW8kUdOuNZZEAgHnHrMajO2cOVV7VoS-zSREf7EoWsjz5sK0r0n-tuCGQCDKCM4Rs',
    coverUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuCpg4Y6K5zbpqXiN75P4dBxZ4_NRUlkoE6fRGDUigucntW9M8pBue0t0ovYsvMvvkO36sg8F7VR4xwCBhHl4UgIMOEVEJqG9JESJ2FpBvF2yELingNeBKfq0vaX7dmH7-vtJEPEgUoHVLXsUanQTxH3hnEs61CyApQN5ZFbHevDLJrvzNeBaG_SfI0i8uErj8x9l2NruuCFd-aais8Q6_baA4VWWhqbGH0EXy_RxL4Cn-8_uiMEkHFH58jT0xYaRv2-knXivHuF4GK7',
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
    avatarUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuCpg4Y6K5zbpqXiN75P4dBxZ4_NRUlkoE6fRGDUigucntW9M8pBue0t0ovYsvMvvkO36sg8F7VR4xwCBhHl4UgIMOEVEJqG9JESJ2FpBvF2yELingNeBKfq0vaX7dmH7-vtJEPEgUoHVLXsUanQTxH3hnEs61CyApQN5ZFbHevDLJrvzNeBaG_SfI0i8uErj8x9l2NruuCFd-aais8Q6_baA4VWWhqbGH0EXy_RxL4Cn-8_uiMEkHFH58jT0xYaRv2-knXivHuF4GK7',
    coverUrl:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuDCBiAi1cOp54U5Wv8LsSxDS6MwnGMHeSYGNyHYOH2bHdyMdyTrPEbGgq2sCdzPAPXLZ8vaVtxJLIN6E90rFc9o9aqxd8zQjRtNDLsQFUL1jjTa7Mt88cRbkaEdST5VFyKy6Dd4GQ07eOaxz0tY0pFNH_blb8dOhTaWJf6qqk9CzfJ--P7hwMUk3WsIlNGKQXpVnGaFLg8GTiPyp8dp7QCrM_R-MLL5x70HdEs0_5oXm5WnJ2-x-lfsOCBEu3wupvgCWF-UR8kPm0us',
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
    clientAvatar:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuAvuTPY5FpVtD8VZQPGm0cn-OHQKuo_a8aLijtbyelfy5abg6YHIAc8QuE6_XqwOwSb_0CkzDGqjUSXa0naYLOAXvA_YY1VCb_ZI1Bm3ddJkPHWQQ4GcNMK5boVRbQXgrWVWk79FMZ5TN6NbFVRNMDV61899Rj-oZG_NROyKZCZAq8Xw7G-0bD_6uJ2Hi1jEynQXQf-_sG4ErSJWoWNKhs6BYl20eRCS_8VYLd794DIo7zvpo7613YCAZtCmnmSVDmLIhStGcExvdT_',
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
    clientAvatar:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuA6SwIXfGsvJhrNsJ43k1zaaBFn_v3jcTQEX3-qkXqODgenFEw953bB8sLrRb6XZ4p4tLjVbgd2SoXsR0Cd2oESO-ZL6q_DL8mG9SlOFQNfpb0J9_D9BL9a-mg8VxGJGhh8ht6aMJns94qtzW0G6q3Ybxp35xIGZNzVXyp67YsREVbIH7B9BcEmJGxFn81ubYLlMGL-0GYFaYONDqqqGWW4Xn7mAEFjbTiUgenNtCbqpxltI8ZO_lyter00PeT2Ze99NeAD9XoEuHEm',
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
    clientAvatar:
      'https://lh3.googleusercontent.com/aida-public/AB6AXuCw5wrSHLRi9mpgNKr_vaW23ci4_ecAOCdXOBvv4ywbmm03i5mHMyCH6AAv7z_mVzNMN5yGH8_IzysG1j4Csi8L7pqFqAXxknY-4x8qIdyBSpvjdwqYhFuTxuPgFvee1h_4mf7UhyaPYeQHyG8rI67tlwULoR3ypf3WVbKvA0ClCZ_5Srw_gd8-qWTm5WgG-1zzgveXtbIxrUYOl7dGPS9OFjk0EQBAM69kDTDItKsRrcbsl-lpD9-z5p4-nR-wCravTMPLdN7fEcVh',
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
