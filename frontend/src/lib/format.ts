// Plain space thousands-separator (not `toLocaleString('fr-FR')`'s narrow
// no-break space, U+202F) — the literal style already used across the app
// for FCFA amounts.
export function formatFcfa(amount: number): string {
  return `${Math.round(amount).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ' ')} FCFA`;
}
