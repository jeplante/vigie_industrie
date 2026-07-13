import type { VigieDataset } from "../domain/models";

export const CSV_HEADERS = [
  "Compagnie",
  "Ticker",
  "Période",
  "Indicateur",
  "Valeur numérique",
  "Valeur affichée",
  "Unité",
  "Valeur comparative",
  "Delta",
  "Direction",
  "Source",
  "Date de publication",
  "Méthode d’extraction",
  "Statut de qualité",
  "Note",
];

const escapeCsv = (value: string | number | null): string =>
  `"${String(value ?? "").replaceAll('"', '""')}"`;

export function createCsv(dataset: VigieDataset): string {
  const rows: Array<Array<string | number | null>> = [CSV_HEADERS];
  for (const observation of dataset.observations) {
    const company = dataset.companies.find(
      ({ id }) => id === observation.companyId,
    );
    rows.push([
      company?.name ?? observation.companyId,
      company?.ticker ?? "",
      observation.period.label,
      observation.label,
      observation.value,
      observation.displayValue,
      observation.unit,
      observation.comparison.value,
      observation.comparison.displayChange,
      observation.direction,
      observation.source.url,
      observation.source.publishedAt,
      observation.quality.extractionMethod,
      observation.quality.status,
      observation.note,
    ]);
  }
  return `\uFEFF${rows.map((row) => row.map(escapeCsv).join(",")).join("\r\n")}`;
}

export function downloadCsv(dataset: VigieDataset): void {
  const url = URL.createObjectURL(
    new Blob([createCsv(dataset)], { type: "text/csv;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = "vigie-assurance-canada.csv";
  link.click();
  URL.revokeObjectURL(url);
}
