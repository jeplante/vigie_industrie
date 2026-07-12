import type { DatasetManifest, QualityReport, VigieDataset } from './models';

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const requireString = (record: Record<string, unknown>, key: string): void => {
  if (typeof record[key] !== 'string' || record[key] === '') {
    throw new Error(`Champ JSON invalide: ${key}`);
  }
};

export function validateDataset(value: unknown): VigieDataset {
  if (!isRecord(value)) throw new Error('Le jeu de données doit être un objet.');
  requireString(value, 'schemaVersion');
  requireString(value, 'generatedAt');
  for (const key of ['companies', 'periods', 'observations', 'news']) {
    if (!Array.isArray(value[key])) throw new Error(`Collection JSON absente: ${key}`);
  }
  if ((value.companies as unknown[]).length === 0) throw new Error('Aucune compagnie publiée.');
  if ((value.observations as unknown[]).length === 0) throw new Error('Aucune observation publiée.');
  return value as unknown as VigieDataset;
}

export function validateManifest(value: unknown): DatasetManifest {
  if (!isRecord(value)) throw new Error('Le manifeste doit être un objet.');
  requireString(value, 'generatedAt');
  requireString(value, 'datasetHash');
  return value as unknown as DatasetManifest;
}

export function validateQualityReport(value: unknown): QualityReport {
  if (!isRecord(value)) throw new Error('Le rapport de qualité doit être un objet.');
  requireString(value, 'generatedAt');
  if (!['success', 'partial', 'failed'].includes(String(value.status))) {
    throw new Error('Statut de qualité inconnu.');
  }
  return value as unknown as QualityReport;
}
