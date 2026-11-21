import type { ArtisanZone } from '../../types';

/** Réponse de `GET /artisans/me/zone` (backend app/schemas/artisans.py ArtisanZoneOut). */
export interface BackendArtisanZone {
  placed: boolean;
  source: 'neighborhood' | 'gps' | null;
  neighborhood: { id: string; label: string; department_label: string } | null;
  trades: {
    id: string;
    trade: { code: string; label_fr: string };
    service_radius_m: number;
    has_custom_service_area: boolean;
  }[];
  radius_max_m: number;
  gps_grid_m: number;
  changes_remaining_short: number;
  changes_remaining_long: number;
  short_window_hours: number;
  long_window_days: number;
  next_change_at: string | null;
}

export function mapArtisanZone(body: BackendArtisanZone): ArtisanZone {
  return {
    placed: body.placed,
    source: body.source,
    neighborhood: body.neighborhood
      ? {
          id: body.neighborhood.id,
          label: body.neighborhood.label,
          departmentLabel: body.neighborhood.department_label,
        }
      : null,
    trades: body.trades.map((trade) => ({
      id: trade.id,
      tradeCode: trade.trade.code,
      tradeLabel: trade.trade.label_fr,
      serviceRadiusM: trade.service_radius_m,
      hasCustomServiceArea: trade.has_custom_service_area,
    })),
    radiusMaxM: body.radius_max_m,
    gpsGridM: body.gps_grid_m,
    changesRemainingShort: body.changes_remaining_short,
    changesRemainingLong: body.changes_remaining_long,
    shortWindowHours: body.short_window_hours,
    longWindowDays: body.long_window_days,
    nextChangeAt: body.next_change_at,
  };
}
