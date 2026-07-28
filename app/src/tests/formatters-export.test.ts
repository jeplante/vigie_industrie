import { describe, expect, it } from "vitest";
import { formatNumericValue } from "../formatters/currency";
import { formatChange } from "../formatters/percentage";
import { createCsv } from "../export/export-csv";
import { dataset } from "./fixtures";

describe("formatage et export", () => {
  it("formate les devises et variations en français", () => {
    expect(formatNumericValue(1.25, "CAD_PER_SHARE")).toContain("1,25");
    expect(formatNumericValue(3.1, "CAD_TRILLION")).toContain("Bil $");
    expect(formatChange(0.125, "PERCENT")).toBe("+13 %");
  });

  it("produit un CSV Excel avec BOM, sources, qualité et guillemets échappés", () => {
    const csv = createCsv(dataset);
    expect(csv.startsWith("\uFEFF")).toBe(true);
    expect(csv).toContain("https://example.com/source");
    expect(csv).toContain("validated");
    expect(csv).toContain('"Note ""citée"""');
  });

  it("exporte les alias sous leurs libellés KPI canoniques", () => {
    const reference = dataset.observations[0]!;
    const csv = createCsv({
      ...dataset,
      observations: [
        {
          ...reference,
          id: "SLF-2025-T1-underlying-net-income",
          companyId: "SLF",
          metricId: "net_income",
          label: "Revenu net sous-jacent",
          note: "Underlying net income.",
        },
        {
          ...reference,
          id: "IAG-2025-T1-solvency-ratio",
          companyId: "IAG",
          metricId: "solvency_ratio",
          label: "Ratio de solvabilité",
          note: "Solvency ratio.",
        },
      ],
    });

    expect(csv).toContain("Résultat des activités de base (core earnings)");
    expect(csv).toContain("Ratio LICAT / solvabilité");
    expect(csv).not.toContain('"Revenu net sous-jacent"');
  });
});
