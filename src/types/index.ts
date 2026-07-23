export type UserRole = 'client' | 'artisan';

export interface Review {
  id: string;
  author: string;
  avatarInitials: string;
  rating: number;
  date: string;
  comment: string;
}

export interface Realisation {
  id: string;
  title: string;
  imageUrl: string;
  altText: string;
}

export interface Artisan {
  id: string;
  name: string;
  trade: string; // e.g., 'Plomberie', 'Électricité', 'Climatisation'
  avatarUrl: string;
  coverUrl: string;
  verified: boolean;
  rating: number;
  reviewCount: number;
  distance: string;
  location: string;
  priceBase: string; // e.g. "15.000 CFA"
  priceNumber: number;
  tags: string[];
  bio: string;
  stats: {
    chantiers: string; // e.g. "150+"
    responseTime: string; // e.g. "< 1h"
    experience: string; // e.g. "8 ans"
  };
  realisations: Realisation[];
  reviews: Review[];
  available: boolean;
}

export interface DevisProposal {
  id: string;
  title: string;
  laborPrice: number; // e.g. 8000
  materialsPrice: number; // e.g. 4000
  totalPrice: number; // e.g. 12000
  currency: string; // "FCFA"
  status: 'pending' | 'accepted' | 'declined';
  date: string;
}

export interface ChatMessage {
  id: string;
  sender: 'client' | 'artisan' | 'system';
  text?: string;
  timestamp: string;
  devis?: DevisProposal;
  photoUrl?: string;
}

export interface JobRequest {
  id: string;
  clientName: string;
  clientAvatar: string;
  title: string;
  trade: string;
  location: string;
  timeAgo: string;
  estimatedPrice: string;
  status: 'new' | 'accepted' | 'completed';
  description?: string;
}

export interface AIAnalysisResult {
  trade: string;
  priceEstimate: string;
  recommendedCount: number;
  explanation: string;
  urgency: string;
  suggestedDevis: {
    title: string;
    labor: number;
    materials: number;
    total: number;
  };
}

export interface WeeklyRevenuePoint {
  label: string; // e.g. "Semaine 1", "Cette semaine"
  amount: number; // FCFA
  isCurrent: boolean;
}

export interface ArtisanStats {
  monthlyRevenue: number; // FCFA
  monthlyRevenueChangePercent: number; // vs mois dernier
  weeklyRevenues: WeeklyRevenuePoint[];
  acceptedRequestsCount: number;
  averageRating: number;
  responseRatePercent: number;
}

export interface CurrentUser {
  id: string;
  name: string;
  initials: string;
  verified: boolean;
  artisanId: string; // linked artisan profile when switching to "Pro" mode
}
