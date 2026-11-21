import type { NeighborhoodCatalog } from '../lib/places';

/**
 * Jeu de données de TEST uniquement (jamais importé par l'application) :
 * un extrait de la réponse de `GET /api/v1/meta/neighborhoods`, valeurs
 * recopiées du serveur (backend/app/core/neighborhoods.py), qui reste la
 * seule source de la liste.
 */
export const TEST_CATALOG: NeighborhoodCatalog = {
  items: [
    {
      id: 'plateau',
      label: 'Dakar-Plateau',
      commune: 'Commune de Dakar-Plateau',
      department: 'dakar',
      departmentLabel: 'Dakar',
      lat: 14.66732,
      lng: -17.43797,
    },
    {
      id: 'medina',
      label: 'Médina',
      commune: 'Commune de Médina',
      department: 'dakar',
      departmentLabel: 'Dakar',
      lat: 14.68049,
      lng: -17.45093,
    },
    {
      id: 'ouakam',
      label: 'Ouakam',
      commune: 'Commune de Ouakam',
      department: 'dakar',
      departmentLabel: 'Dakar',
      lat: 14.72474,
      lng: -17.48507,
    },
    {
      id: 'point-e',
      label: 'Fann-Point E-Amitié',
      commune: 'Commune de Fann-Point E-Amitié',
      department: 'dakar',
      departmentLabel: 'Dakar',
      lat: 14.69403,
      lng: -17.46213,
    },
    {
      id: 'ngor',
      label: 'Ngor',
      commune: 'Commune de Ngor',
      department: 'dakar',
      departmentLabel: 'Dakar',
      lat: 14.74879,
      lng: -17.51496,
    },
    {
      id: 'yoff',
      label: 'Yoff',
      commune: 'Commune de Yoff',
      department: 'dakar',
      departmentLabel: 'Dakar',
      lat: 14.76036,
      lng: -17.46815,
    },
    {
      id: 'bargny',
      label: 'Bargny',
      commune: 'Commune de Bargny',
      department: 'rufisque',
      departmentLabel: 'Rufisque',
      lat: 14.69383,
      lng: -17.22974,
    },
  ],
  aliases: { almadies: 'ngor', 'yoff-ngor': 'yoff' },
  defaultId: 'plateau',
  serviceRegion: { center: { lat: 14.7394, lng: -17.3348 }, radiusM: 30_000 },
};

/** Chargeur de catalogue pour `PlaceProvider` dans les tests. */
export const loadTestCatalog = async (): Promise<NeighborhoodCatalog> => TEST_CATALOG;
