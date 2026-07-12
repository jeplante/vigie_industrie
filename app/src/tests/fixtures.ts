import type {
  CompanyId,
  DatasetManifest,
  Observation,
  Period,
  PeriodKey,
  QualityReport,
  VigieDataset,
} from "../domain/models";

const period = (year: number, periodKey: PeriodKey): Period => {
  const quarter = periodKey === "AN" ? null : Number(periodKey.slice(1));
  const monthDay = { T1: "03-31", T2: "06-30", T3: "09-30", AN: "12-31" }[
    periodKey
  ];
  return {
    periodId: `${year}-${periodKey}`,
    periodKey,
    type: periodKey === "AN" ? "annual" : "quarter",
    year,
    quarter,
    endDate: `${year}-${monthDay}`,
    label: periodKey === "AN" ? `Annuel ${year}` : `${periodKey} ${year}`,
  };
};

const periods = [
  period(2025, "T1"),
  period(2025, "T2"),
  period(2025, "T3"),
  period(2025, "AN"),
  period(2026, "T1"),
  period(2026, "T2"),
];

const observation = (
  companyId: CompanyId,
  value: number,
  current: Period,
): Observation => {
  const previousId = `${current.year - 1}-${current.periodKey}`;
  return {
    id: `${companyId}-${current.periodId}-core_eps`,
    companyId,
    period: current,
    metricId: "core_eps",
    label: "BPA de base",
    value,
    unit: "CAD_PER_SHARE",
    displayValue: `${value.toFixed(2).replace(".", ",")} $`,
    comparison: {
      periodId: previousId,
      value: value - 0.25,
      displayValue: `${(value - 0.25).toFixed(2).replace(".", ",")} $`,
      periodLabel:
        current.periodKey === "AN"
          ? `Annuel ${current.year - 1}`
          : `${current.periodKey} ${current.year - 1}`,
      change: 0.1,
      changeUnit: "PERCENT",
      displayChange: "+10 %",
    },
    direction: "up",
    note: 'Note "citée"',
    source: {
      sourceId: `${String(companyId).toLowerCase()}-results`,
      url: "https://example.com/source",
      title: `Résultats ${current.label}`,
      publishedAt: current.endDate,
      fetchedAt: "2026-07-10T12:00:00Z",
      documentHash: `sha256:${"a".repeat(64)}`,
      priority: "primary",
    },
    quality: {
      status: "validated",
      extractionMethod: "deterministic",
      confidence: 1,
      warnings: [],
    },
  };
};

export const dataset: VigieDataset = {
  schemaVersion: "2.0.0",
  generatedAt: "2026-07-10T12:00:00Z",
  companies: [
    {
      id: "MFC",
      name: "Manuvie",
      fullName: "Manuvie",
      ticker: "MFC.TO",
      investorRelationsUrl: "https://example.com/mfc",
    },
    {
      id: "SLF",
      name: "Sun Life",
      fullName: "Sun Life",
      ticker: "SLF.TO",
      investorRelationsUrl: "https://example.com/slf",
    },
  ],
  periods,
  observations: [
    ...periods.map((item, index) => observation("MFC", 1.25 + index, item)),
    ...periods
      .slice(0, 4)
      .map((item, index) => observation("SLF", 2.25 + index, item)),
  ],
  news: [
    {
      id: "news-mfc-2026-t2",
      companyIds: ["MFC"],
      periodId: "2026-T2",
      periodKey: "T2",
      publishedAt: "2026-05-01",
      source: {
        type: "official_ir",
        name: "Manuvie",
        url: "https://example.com/news-mfc",
      },
      title: "Résultats du trimestre",
      originalSummary: "Résumé.",
      generatedSummary: null,
      categories: ["financial_results"],
      importance: "high",
      themes: ["résultats"],
      quality: {
        status: "validated",
        extractionMethod: "deterministic",
        confidence: 1,
        warnings: [],
      },
    },
    {
      id: "news-slf-2025-an",
      companyIds: ["SLF"],
      periodId: "2025-AN",
      periodKey: "AN",
      publishedAt: "2025-11-01",
      source: {
        type: "official_ir",
        name: "Sun Life",
        url: "https://example.com/news-slf",
      },
      title: "Résultats annuels",
      originalSummary: "Résumé.",
      generatedSummary: null,
      categories: ["financial_results"],
      importance: "high",
      themes: ["résultats"],
      quality: {
        status: "validated",
        extractionMethod: "deterministic",
        confidence: 1,
        warnings: [],
      },
    },
  ],
};

export const manifest: DatasetManifest = {
  schemaVersion: "1.0.0",
  generatedAt: "2026-07-10T12:00:00Z",
  datasetHash: `sha256:${"a".repeat(64)}`,
  observationCount: 10,
  newsCount: 2,
  companyCount: 2,
  lastSuccessfulRefresh: "2026-07-10T12:00:00Z",
  companyFreshness: [
    {
      companyId: "MFC",
      latestAvailablePeriodId: "2026-T2",
      latestPublishedPeriodId: "2026-T2",
      latestSourceCheckAt: "2026-07-10T12:00:00Z",
      freshnessStatus: "current",
    },
    {
      companyId: "SLF",
      latestAvailablePeriodId: "2026-T1",
      latestPublishedPeriodId: "2025-AN",
      latestSourceCheckAt: "2026-07-10T12:00:00Z",
      freshnessStatus: "stale",
    },
  ],
};

export const quality: QualityReport = {
  generatedAt: "2026-07-10T12:00:00Z",
  status: "success",
  sourcesChecked: 2,
  sourcesSucceeded: 2,
  sourcesFailed: 0,
  observationsAdded: 0,
  observationsUpdated: 0,
  overridesApplied: 0,
  warnings: [],
  errors: [],
};
