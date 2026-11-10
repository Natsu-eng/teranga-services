import React from 'react';
import {
  ArrowRight,
  Lock,
  MessageSquareQuote,
  MessageSquareText,
  ReceiptText,
  UserCheck,
} from 'lucide-react';
import { Link } from 'react-router';
import { ButtonLink } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Logo } from '../../components/ui/Logo';
import { SafeImage } from '../../components/ui/SafeImage';
import { VerifiedBadge } from '../../components/ui/VerifiedBadge';

/*
 * Promesses affichées : uniquement ce que le produit garantit réellement
 * aujourd'hui (aucun chiffre inventé, aucune fonctionnalité absente comme
 * le paiement en ligne).
 */
const TRUST_POINTS = [
  {
    icon: <MessageSquareQuote aria-hidden className="w-5 h-5" />,
    title: 'Avis authentiques',
    text: 'Seul un client dont l’intervention est terminée peut laisser un avis.',
  },
  {
    icon: <Lock aria-hidden className="w-5 h-5" />,
    title: 'Coordonnées protégées',
    text: 'Aucun numéro de téléphone n’est affiché publiquement sur Téranga.',
  },
] as const;

const STEPS = [
  {
    icon: <MessageSquareText aria-hidden className="w-5 h-5" />,
    title: 'Décrivez votre besoin',
    text: 'Quelques phrases suffisent : nous identifions le métier concerné.',
  },
  {
    icon: <UserCheck aria-hidden className="w-5 h-5" />,
    title: 'Choisissez un artisan',
    text: 'Comparez les profils vérifiés, leurs avis et leur distance.',
  },
  {
    icon: <ReceiptText aria-hidden className="w-5 h-5" />,
    title: 'Recevez un devis',
    text: 'Acceptez-le dans l’application, puis notez l’intervention.',
  },
] as const;

/**
 * Accueil marketing (/). Première impression de la « confiance
 * chaleureuse » : photo d'artisan, titre Fraunces, une seule action
 * principale en or, et le badge Vérifié montré tel qu'il apparaît ensuite
 * sur chaque carte.
 */
export const LandingScreen: React.FC = () => (
  <div className="min-h-screen bg-background">
    <section className="relative h-[46vh] min-h-72 max-h-[30rem] overflow-hidden rounded-b-sheet">
      <SafeImage
        src="/images/hero-plombier.jpg"
        fallback="/images/placeholder-cover.svg"
        alt="Un artisan plombier au travail"
        loading="eager"
        fetchPriority="high"
        className="absolute inset-0 w-full h-full object-cover object-top"
      />
      {/* Voile dégradé : assure la lisibilité du logo et fond l'image dans la page. */}
      <div
        aria-hidden
        className="absolute inset-0 bg-linear-to-b from-primary/35 via-transparent to-background"
      />
      <div className="absolute top-4 left-4 md:left-8 rounded-full bg-surface/90 backdrop-blur-sm px-3 py-1.5 shadow-card">
        <Logo />
      </div>
    </section>

    <main className="relative z-10 -mt-20 px-4 md:px-8 pb-12 max-w-3xl mx-auto space-y-10">
      <Card padding="lg" className="text-center space-y-5">
        <p className="text-caption font-semibold uppercase tracking-[0.14em] text-accent-foreground">
          Artisans de confiance au Sénégal
        </p>
        <h1 className="font-display text-display-lg md:text-display-xl font-semibold text-primary max-w-lg mx-auto">
          Un artisan de confiance, en quelques secondes
        </h1>
        <p className="text-base text-muted-foreground max-w-md mx-auto leading-relaxed">
          Plomberie, électricité, climatisation… Décrivez votre besoin, nous vous mettons en
          relation avec des artisans vérifiés près de chez vous.
        </p>
        <div className="flex flex-col items-center gap-2 pt-1 max-w-xs mx-auto">
          <ButtonLink
            to="/accueil"
            variant="primary"
            size="lg"
            fullWidth
            trailingIcon={<ArrowRight aria-hidden className="w-5 h-5" />}
          >
            Trouver un artisan
          </ButtonLink>
          <ButtonLink to="/connexion" variant="ghost" fullWidth>
            Vous êtes artisan ? Rejoignez Téranga Pro
          </ButtonLink>
        </div>
      </Card>

      <section aria-labelledby="confiance" className="space-y-4">
        <h2 id="confiance" className="font-display text-display-sm font-semibold text-primary">
          La confiance, avant tout
        </h2>
        <ul className="grid gap-3 md:grid-cols-3">
          <li>
            <Card className="h-full flex flex-col gap-3">
              <VerifiedBadge size="md" className="self-start" />
              <div className="space-y-1">
                <h3 className="font-display text-title font-semibold text-foreground">
                  Artisans vérifiés
                </h3>
                <p className="text-sm text-muted-foreground">
                  Identité et documents contrôlés par notre équipe avant toute mise en relation.
                </p>
              </div>
            </Card>
          </li>
          {TRUST_POINTS.map((point) => (
            <li key={point.title}>
              <Card className="h-full flex flex-col gap-3">
                <span className="inline-flex w-9 h-9 items-center justify-center rounded-full bg-emerald-tint text-primary-emerald">
                  {point.icon}
                </span>
                <div className="space-y-1">
                  <h3 className="font-display text-title font-semibold text-foreground">
                    {point.title}
                  </h3>
                  <p className="text-sm text-muted-foreground">{point.text}</p>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="etapes" className="space-y-4">
        <h2 id="etapes" className="font-display text-display-sm font-semibold text-primary">
          Comment ça marche
        </h2>
        <ol className="space-y-3">
          {STEPS.map((step, index) => (
            <li key={step.title}>
              <Card tone="tint" className="flex items-start gap-4">
                <span className="relative inline-flex w-10 h-10 shrink-0 items-center justify-center rounded-full bg-surface text-primary-emerald shadow-card">
                  {step.icon}
                  <span className="absolute -top-1 -right-1 inline-flex w-5 h-5 items-center justify-center rounded-full bg-accent text-primary text-caption font-bold">
                    {index + 1}
                  </span>
                </span>
                <div className="space-y-0.5">
                  <h3 className="font-display text-title font-semibold text-foreground">
                    {step.title}
                  </h3>
                  <p className="text-sm text-muted-foreground">{step.text}</p>
                </div>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      <footer className="pt-2 text-center text-sm text-muted-foreground space-y-1">
        <p>© Téranga Services — Dakar</p>
        <Link
          to="/connexion"
          className="font-semibold text-primary underline-offset-4 hover:underline"
        >
          Se connecter
        </Link>
      </footer>
    </main>
  </div>
);
