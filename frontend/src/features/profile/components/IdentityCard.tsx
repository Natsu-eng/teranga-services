import React, { useState } from 'react';
import { Pencil, UserRoundPen } from 'lucide-react';
import { Avatar } from '../../../components/ui/Avatar';
import { Button } from '../../../components/ui/Button';
import { Card } from '../../../components/ui/Card';
import { TextField } from '../../../components/ui/Field';
import { IconButton } from '../../../components/ui/IconButton';
import { ApiError } from '../../../lib/api';
import { hasRealName } from '../../../lib/identity';
import { useAuth } from '../../auth/hooks/useAuth';

interface IdentityCardProps {
  name: string;
  avatarUrl?: string | null;
  /** Ligne sous le nom (rôle, quartier...). */
  subtitle: React.ReactNode;
  /** Badge ou pastille à côté du sous-titre (ex. Vérifié). */
  badge?: React.ReactNode;
  /** Numéro de connexion, rappelé en lecture seule. */
  phone?: string | null;
}

/**
 * Identité du compte, commune aux profils client et artisan : avatar, nom
 * modifiable (PATCH /users/me via `auth.updateFullName`), numéro de
 * connexion en lecture seule.
 *
 * Compte hérité dont le « nom » est resté le numéro (avant le correctif de
 * confidentialité) : on le dit clairement et on invite à saisir un vrai nom,
 * au lieu d'afficher le numéro comme s'il s'agissait d'un nom.
 */
export const IdentityCard: React.FC<IdentityCardProps> = ({
  name,
  avatarUrl,
  subtitle,
  badge,
  phone,
}) => {
  const auth = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const knownName = hasRealName(name);

  const startEditing = () => {
    // Un numéro resté en guise de nom n'est jamais proposé comme valeur de départ.
    setDraft(knownName ? name : '');
    setError(null);
    setIsEditing(true);
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setIsSaving(true);
    try {
      await auth.updateFullName(draft);
      setIsEditing(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Une erreur est survenue. Merci de réessayer.',
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card padding="lg" className="space-y-4">
      <div className="flex items-center gap-4">
        <Avatar name={name} src={avatarUrl} size="lg" decorative />
        <div className="min-w-0 flex-1 space-y-1">
          {isEditing ? (
            <form onSubmit={handleSave} className="space-y-2">
              <TextField
                label="Nom complet"
                hideLabel
                autoComplete="name"
                autoFocus
                minLength={2}
                maxLength={150}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Prénom et nom"
                error={error}
              />
              <div className="flex items-center gap-2">
                <Button type="submit" variant="brand" size="sm" isLoading={isSaving}>
                  {isSaving ? 'Enregistrement...' : 'Enregistrer'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={isSaving}
                  onClick={() => setIsEditing(false)}
                >
                  Annuler
                </Button>
              </div>
            </form>
          ) : (
            <div className="flex items-center gap-1">
              <h1 className="font-display text-display-sm font-semibold text-primary truncate">
                {knownName ? name : 'Nom à compléter'}
              </h1>
              <IconButton label="Modifier mon nom" size="sm" onClick={startEditing}>
                <Pencil aria-hidden className="w-4 h-4" />
              </IconButton>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            {subtitle}
            {badge}
          </div>
        </div>
      </div>

      {!knownName && !isEditing && (
        <div className="rounded-field bg-accent-soft p-3 flex items-start gap-3 text-sm text-accent-foreground-strong">
          <UserRoundPen aria-hidden className="w-5 h-5 shrink-0" />
          <div className="space-y-2">
            <p>
              Votre compte n&apos;a pas encore de nom : ajoutez-le pour que les{' '}
              {auth.role === 'artisan' ? 'clients' : 'artisans'} sachent à qui ils ont affaire.
            </p>
            <Button variant="outline" size="sm" onClick={startEditing}>
              Ajouter mon nom
            </Button>
          </div>
        </div>
      )}

      {phone && (
        <p className="text-sm text-muted-foreground border-t border-border-faint pt-3">
          Numéro de connexion : <span className="font-medium text-foreground">{phone}</span>
          <span className="block text-xs">
            Il sert uniquement à vous connecter et n&apos;est jamais affiché publiquement.
          </span>
        </p>
      )}
    </Card>
  );
};
