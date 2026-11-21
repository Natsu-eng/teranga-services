import type { NeighborhoodCatalog } from '../places';
import { apiRequest } from './http';

/** Réponse de `GET /api/v1/meta/neighborhoods` (backend app/schemas/meta.py). */
interface BackendNeighborhoods {
  items: {
    id: string;
    label: string;
    commune: string;
    department: string;
    department_label: string;
    lat: number;
    lng: number;
  }[];
  aliases: Record<string, string>;
  default_id: string;
  service_region: { center_lat: number; center_lng: number; radius_m: number };
}

export function mapNeighborhoods(body: BackendNeighborhoods): NeighborhoodCatalog {
  return {
    items: body.items.map((item) => ({
      id: item.id,
      label: item.label,
      commune: item.commune,
      department: item.department,
      departmentLabel: item.department_label,
      lat: item.lat,
      lng: item.lng,
    })),
    aliases: body.aliases,
    defaultId: body.default_id,
    serviceRegion: {
      center: { lat: body.service_region.center_lat, lng: body.service_region.center_lng },
      radiusM: body.service_region.radius_m,
    },
  };
}

/** Liste fermée des quartiers desservis et région desservie : lecture publique. */
export async function fetchNeighborhoods(): Promise<NeighborhoodCatalog> {
  return mapNeighborhoods(
    await apiRequest<BackendNeighborhoods>('/meta/neighborhoods', { skipAuth: true }),
  );
}
