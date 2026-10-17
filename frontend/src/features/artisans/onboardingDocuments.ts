/**
 * Documents de vérification exigés à l'onboarding artisan, leur statut
 * affiché, et le document le plus récent par type. Extraits de
 * `ArtisanOnboardingScreen.tsx` sans changement.
 */
import type { StatusTone } from '../../components/ui/StatusPill';
import type { VerificationDocType, VerificationDocument, VerificationDocStatus } from '../../types';

export const REQUIRED_DOCS: { type: VerificationDocType; label: string; hint: string }[] = [
  { type: 'cni', label: "Carte d'identité (CNI)", hint: 'Recto lisible — image ou PDF' },
  { type: 'selfie', label: 'Selfie', hint: 'Votre visage bien visible — image uniquement' },
];

export const DOC_STATUS: Record<VerificationDocStatus, { label: string; tone: StatusTone }> = {
  pending: { label: 'En attente de revue', tone: 'warning' },
  approved: { label: 'Validé', tone: 'success' },
  rejected: { label: 'Refusé', tone: 'danger' },
};

export function latestDocumentsByType(
  documents: VerificationDocument[],
): Partial<Record<VerificationDocType, VerificationDocument>> {
  const result: Partial<Record<VerificationDocType, VerificationDocument>> = {};
  for (const doc of documents) {
    const current = result[doc.docType];
    if (!current || new Date(doc.createdAt).getTime() > new Date(current.createdAt).getTime()) {
      result[doc.docType] = doc;
    }
  }
  return result;
}
