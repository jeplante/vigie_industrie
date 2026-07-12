import type { DatasetManifest, QualityReport, VigieDataset } from "./models";

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const requireString = (record: Record<string, unknown>, key: string): void => {
  if (typeof record[key] !== "string" || record[key] === "") {
    throw new Error(`Champ JSON invalide: ${key}`);
  }
};

export function validateDataset(value: unknown): VigieDataset {
  if (!isRecord(value))
    throw new Error("Le jeu de données doit être un objet.");
  requireString(value, "schemaVersion");
  requireString(value, "generatedAt");
  for (const key of ["companies", "periods", "observations", "news"]) {
    if (!Array.isArray(value[key]))
      throw new Error(`Collection JSON absente: ${key}`);
  }
  if ((value.companies as unknown[]).length === 0)
    throw new Error("Aucune compagnie publiée.");
  if ((value.observations as unknown[]).length === 0)
    throw new Error("Aucune observation publiée.");
  const periodIds = new Set<string>();
  for (const entry of value.periods as unknown[]) {
    if (!isRecord(entry)) throw new Error("Période JSON invalide.");
    requireString(entry, "periodId");
    requireString(entry, "periodKey");
    if (!Number.isInteger(entry.year))
      throw new Error("Année de période invalide.");
    const expectedId = `${String(entry.year)}-${String(entry.periodKey)}`;
    if (entry.periodId !== expectedId)
      throw new Error(
        `Identifiant de période invalide: ${String(entry.periodId)}`,
      );
    if (periodIds.has(String(entry.periodId)))
      throw new Error(`Période dupliquée: ${String(entry.periodId)}`);
    periodIds.add(String(entry.periodId));
  }
  for (const entry of value.observations as unknown[]) {
    if (
      !isRecord(entry) ||
      !isRecord(entry.period) ||
      !periodIds.has(String(entry.period.periodId))
    ) {
      throw new Error("Observation associée à une période inconnue.");
    }
  }
  for (const entry of value.news as unknown[]) {
    if (!isRecord(entry) || !periodIds.has(String(entry.periodId))) {
      throw new Error("Actualité associée à une période inconnue.");
    }
  }
  return value as unknown as VigieDataset;
}

export function validateManifest(value: unknown): DatasetManifest {
  if (!isRecord(value)) throw new Error("Le manifeste doit être un objet.");
  requireString(value, "generatedAt");
  requireString(value, "datasetHash");
  if (!Array.isArray(value.companyFreshness)) {
    throw new Error("Fraîcheur par compagnie absente du manifeste.");
  }
  return value as unknown as DatasetManifest;
}

export function validateQualityReport(value: unknown): QualityReport {
  if (!isRecord(value))
    throw new Error("Le rapport de qualité doit être un objet.");
  requireString(value, "generatedAt");
  if (!["success", "partial", "failed"].includes(String(value.status))) {
    throw new Error("Statut de qualité inconnu.");
  }
  return value as unknown as QualityReport;
}
