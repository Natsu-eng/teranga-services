import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { Avatar } from './Avatar';
import { Card } from './Card';
import { Chip } from './Chip';
import { Logo } from './Logo';
import { Rating, RatingInput, StarRow } from './Rating';
import { SectionHeader } from './SectionHeader';
import { StatTile } from './StatTile';
import { StatusPill } from './StatusPill';
import { Switch } from './Switch';
import { VerifiedBadge } from './VerifiedBadge';

afterEach(cleanup);

describe('VerifiedBadge', () => {
  it('affiche « Vérifié » sur une pastille émeraude pleine, texte blanc', () => {
    render(<VerifiedBadge />);

    const badge = screen.getByText('Vérifié');
    expect(badge.className).toContain('bg-primary-emerald');
    expect(badge.className).toContain('text-white');
    expect(badge).toHaveAttribute('title', expect.stringContaining('vérifiés'));
  });

  it('propose une grande taille pour la fiche artisan', () => {
    render(<VerifiedBadge size="lg" />);

    expect(screen.getByText('Vérifié').className).toContain('h-9');
  });
});

describe('Avatar', () => {
  it('affiche les initiales colorées quand il n’y a pas de photo', () => {
    render(<Avatar name="Awa Diop" />);

    const avatar = screen.getByRole('img', { name: 'Awa Diop' });
    expect(avatar).toHaveTextContent('AD');
  });

  it('affiche la photo réelle (chargée en lazy) quand une URL est fournie', () => {
    render(<Avatar name="Awa Diop" src="https://exemple.sn/awa.jpg" />);

    const image = screen.getByRole('img', { name: 'Awa Diop' });
    expect(image.tagName).toBe('IMG');
    expect(image).toHaveAttribute('src', 'https://exemple.sn/awa.jpg');
    expect(image).toHaveAttribute('loading', 'lazy');
  });

  it('bascule sur les initiales quand la photo ne se charge pas', () => {
    render(<Avatar name="Awa Diop" src="https://exemple.sn/cassee.jpg" />);

    fireEvent.error(screen.getByRole('img', { name: 'Awa Diop' }));

    const fallback = screen.getByRole('img', { name: 'Awa Diop' });
    expect(fallback.tagName).toBe('SPAN');
    expect(fallback).toHaveTextContent('AD');
  });

  it('attribue toujours la même couleur au même nom', () => {
    const { unmount } = render(<Avatar name="Moussa Fall" />);
    const first = screen.getByRole('img', { name: 'Moussa Fall' }).className;
    unmount();
    render(<Avatar name="Moussa Fall" />);

    expect(screen.getByRole('img', { name: 'Moussa Fall' }).className).toBe(first);
  });

  it('se masque des lecteurs d’écran quand il est décoratif', () => {
    render(<Avatar name="Awa Diop" decorative />);

    expect(screen.queryByRole('img', { name: 'Awa Diop' })).not.toBeInTheDocument();
    expect(screen.getByText('AD')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('Rating', () => {
  it('affiche la note au format français avec le nombre d’avis', () => {
    render(<Rating value={4.83} count={12} />);

    expect(screen.getByText('4,8')).toBeInTheDocument();
    expect(screen.getByText('(12 avis)')).toBeInTheDocument();
    expect(screen.getByText('Note de 4,8 sur 5, 12 avis')).toHaveClass('sr-only');
  });

  it('affiche « Nouveau » et jamais « 0,0 » pour un artisan sans avis', () => {
    render(<Rating value={0} count={0} />);

    expect(screen.getByText('Nouveau')).toBeInTheDocument();
    expect(screen.queryByText('0,0')).not.toBeInTheDocument();
  });

  it('masque le nombre d’avis sur demande', () => {
    render(<Rating value={4.5} count={3} hideCount />);

    expect(screen.queryByText('(3 avis)')).not.toBeInTheDocument();
  });
});

describe('StarRow', () => {
  it('annonce la note individuelle aux lecteurs d’écran', () => {
    render(<StarRow value={4} />);

    expect(screen.getByText('Note : 4 sur 5')).toBeInTheDocument();
  });
});

describe('RatingInput', () => {
  it('expose 5 boutons nommés et remonte la note choisie', () => {
    const onChange = vi.fn();
    render(<RatingInput value={2} onChange={onChange} />);

    expect(screen.getByRole('group', { name: 'Votre note' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '2 étoiles' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    fireEvent.click(screen.getByRole('button', { name: '5 étoiles' }));

    expect(onChange).toHaveBeenCalledWith(5);
  });
});

describe('StatTile', () => {
  it('affiche la valeur et son libellé', () => {
    render(<StatTile label="Revenus" value="45 000 FCFA" hint="ce mois-ci" />);

    expect(screen.getByText('Revenus')).toBeInTheDocument();
    expect(screen.getByText('45 000 FCFA').className).toContain('font-display');
    expect(screen.getByText('ce mois-ci')).toBeInTheDocument();
  });
});

describe('SectionHeader', () => {
  it('rend un titre Fraunces au niveau demandé avec son action', () => {
    render(<SectionHeader as="h3" title="Avis clients" action={<a href="#avis">Voir tout</a>} />);

    const heading = screen.getByRole('heading', { level: 3, name: 'Avis clients' });
    expect(heading.className).toContain('font-display');
    expect(screen.getByRole('link', { name: 'Voir tout' })).toBeInTheDocument();
  });
});

describe('StatusPill', () => {
  it('porte le sens par son texte, renforcé par la tonalité', () => {
    render(<StatusPill tone="danger">Refusé</StatusPill>);

    expect(screen.getByText('Refusé').className).toContain('bg-destructive-soft');
  });
});

describe('Card', () => {
  it('rend une surface blanche arrondie avec ombre douce', () => {
    render(<Card as="section">Contenu</Card>);

    const card = screen.getByText('Contenu');
    expect(card.tagName).toBe('SECTION');
    expect(card.className).toContain('rounded-card');
    expect(card.className).toContain('shadow-card');
  });

  it('signale la tonalité sombre pour adapter le focus', () => {
    render(<Card tone="dark">Résultat</Card>);

    expect(screen.getByText('Résultat')).toHaveAttribute('data-tone', 'dark');
  });
});

describe('Chip', () => {
  it('expose son état sélectionné par aria-pressed', () => {
    const onClick = vi.fn();
    render(
      <>
        <Chip selected>Plomberie</Chip>
        <Chip onClick={onClick}>Électricité</Chip>
      </>,
    );

    expect(screen.getByRole('button', { name: 'Plomberie' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Électricité' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );

    fireEvent.click(screen.getByRole('button', { name: 'Électricité' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe('Switch', () => {
  it('bascule son état via role="switch"', () => {
    const onChange = vi.fn();
    render(<Switch checked={false} onChange={onChange} label="Disponibilité" />);

    const toggle = screen.getByRole('switch', { name: 'Disponibilité' });
    expect(toggle).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(toggle);
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

describe('Logo', () => {
  it('affiche la mention Pro pour l’espace artisan', () => {
    render(<Logo variant="pro" />);

    expect(screen.getByText('Pro')).toBeInTheDocument();
    expect(screen.getByText(/Téranga/)).toBeInTheDocument();
  });
});
