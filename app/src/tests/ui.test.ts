import { describe, expect, it, vi } from "vitest";
import { enableArrowNavigation } from "../ui/accessibility";
import { renderCompanyTabs } from "../ui/render-company-tabs";
import { renderPeriodSelect } from "../ui/render-period-select";
import { renderNews } from "../ui/render-news";
import { renderDashboard } from "../ui/render-dashboard";
import { renderHistory } from "../ui/render-history";
import { renderSummary } from "../ui/render-summary";
import { renderStatus } from "../ui/render-status";
import {
  historicalKpiOptions,
  populateHistoricalKpiSelect,
} from "../ui/history-kpis";
import {
  availablePeriods,
  availablePeriodsForCompany,
  initialState,
  selectCompany,
} from "../ui/state";
import { dataset, manifest, quality } from "./fixtures";

describe("interface", () => {
  it("change de compagnie et de période publiée", () => {
    const companies = document.createElement("div");
    const periods = document.createElement("div");
    const onCompany = vi.fn();
    const onPeriod = vi.fn();
    renderCompanyTabs(companies, dataset, "MFC", onCompany);
    renderPeriodSelect(periods, availablePeriods(dataset), "2025-AN", onPeriod);
    companies.querySelectorAll("button")[1]?.click();
    const select = periods.querySelector("select")!;
    select.value = "2025-T3";
    select.dispatchEvent(new Event("change"));
    expect(onCompany).toHaveBeenCalledWith("SLF");
    expect(onPeriod).toHaveBeenCalledWith("2025-T3");
    expect([...select.options].map((option) => option.value)).toEqual([
      "2026-T2",
      "2026-T1",
      "2025-AN",
      "2025-T3",
      "2025-T2",
      "2025-T1",
    ]);
  });

  it("sélectionne la période récente dès qu’une compagnie la publie", () => {
    const state = initialState(dataset);
    expect(state.periodId).toBe("2026-T2");
    expect(state.viewMode).toBe("summary");
    expect(state.historicalKpi).toBe("metric:core_eps");
    selectCompany(state, "SLF");
    expect(state.periodId).toBe("2026-T2");
    expect(
      availablePeriodsForCompany(dataset, "SLF").map((item) => item.periodId),
    ).toEqual(["2025-AN", "2025-T3", "2025-T2", "2025-T1"]);
  });

  it("affiche les compagnies dans un tableau compact pour une période commune", () => {
    const container = document.createElement("div");
    const onSelect = vi.fn();
    renderSummary(container, dataset, "2025-AN", onSelect);

    const rows = container.querySelectorAll(".summary-company-row");
    expect(rows).toHaveLength(2);
    expect(container.querySelector(".summary-table")).not.toBeNull();
    expect(container.querySelectorAll("thead th")).toHaveLength(2);
    expect(rows[0]?.textContent).toContain("Manuvie");
    expect(rows[1]?.textContent).toContain("Sun Life");
    expect(rows[0]?.querySelectorAll(".summary-metric-cell")).toHaveLength(1);
    expect(rows[1]?.querySelectorAll(".summary-metric-cell")).toHaveLength(1);
    rows[1]?.querySelector<HTMLButtonElement>("button")?.click();
    expect(onSelect).toHaveBeenCalledWith("SLF");
  });

  it("signale les données non publiées dans le tableau de synthèse", () => {
    const container = document.createElement("div");
    renderSummary(container, dataset, "2026-T2", vi.fn());

    const rows = container.querySelectorAll(".summary-company-row");
    expect(rows[0]?.textContent).not.toContain("Données non encore publiées");
    expect(rows[1]?.textContent).toContain("Données non encore publiées");
    expect(rows[1]?.querySelectorAll(".summary-metric-missing")).toHaveLength(
      1,
    );
  });

  it("regroupe les alias core earnings et solvabilité dans les KPI canoniques", () => {
    const reference = dataset.observations.find(
      (item) => item.companyId === "SLF" && item.period.periodId === "2025-T3",
    )!;
    const aliasDataset = {
      ...dataset,
      observations: [
        ...dataset.observations,
        {
          ...reference,
          id: "SLF-2025-T3-underlying-net-income",
          metricId: "net_income",
          label: "Revenu net sous-jacent",
          note: "Underlying net income of $1,050 million.",
          unit: "CAD_BILLION",
          value: 1.05,
          displayValue: "1,05 G$",
        },
        {
          ...reference,
          id: "SLF-2025-T3-solvency",
          metricId: "solvency_ratio",
          label: "Ratio de solvabilité",
          note: "Solvency ratio of 143%.",
          unit: "PERCENT",
          value: 143,
          displayValue: "143 %",
        },
      ],
    };
    const container = document.createElement("div");

    renderSummary(container, aliasDataset, "2025-T3", vi.fn());
    const options = historicalKpiOptions(aliasDataset).map(
      (option) => option.value,
    );

    expect(container.querySelector("thead")?.textContent).toContain(
      "Résultat des activités de base (core earnings)",
    );
    expect(container.querySelector("thead")?.textContent).toContain(
      "Ratio LICAT / solvabilité",
    );
    expect(options).toContain("metric:core_earnings");
    expect(options).toContain("metric:licat_ratio");
    expect(options).not.toContain("metric:solvency_ratio");
  });

  it("fusionne les trois variantes d’actifs en un seul KPI comparable", () => {
    const mfc = dataset.observations.find(
      (item) => item.companyId === "MFC" && item.period.periodId === "2025-T3",
    )!;
    const slf = dataset.observations.find(
      (item) => item.companyId === "SLF" && item.period.periodId === "2025-T3",
    )!;
    const assetsDataset = {
      ...dataset,
      observations: [
        ...dataset.observations,
        {
          ...mfc,
          id: "MFC-2025-T3-assets-under-management",
          metricId: "assets_under_management",
          label: "Actif sous gestion",
          value: 900,
          unit: "CAD_BILLION",
          displayValue: "900 G$",
        },
        {
          ...slf,
          id: "SLF-2025-T3-total-client-assets",
          metricId: "total_client_assets",
          label: "Actifs clients totaux",
          value: 2.5,
          unit: "CAD_TRILLION",
          displayValue: "2,5 Bil $",
        },
      ],
    };
    const container = document.createElement("div");

    renderSummary(container, assetsDataset, "2025-T3", vi.fn());
    const headings = [...container.querySelectorAll("thead th")].map(
      (heading) => heading.textContent,
    );
    const options = historicalKpiOptions(assetsDataset).map(
      (option) => option.value,
    );

    expect(headings.filter((label) => label?.includes("Actifs"))).toEqual([
      "Actifs gérés / administrés",
    ]);
    expect(container.textContent).toContain("900 G$");
    expect(container.textContent).toContain("2,5 Bil $");
    expect(options).toContain("metric:assets_managed_or_administered");
    expect(options).not.toContain("metric:assets_under_management");
    expect(options).not.toContain("metric:assets_under_administration");
    expect(options).not.toContain("metric:total_client_assets");
  });

  it("offre les périodes récentes partielles et les anciennes périodes communes", () => {
    expect(availablePeriods(dataset).map((item) => item.periodId)).toEqual([
      "2026-T2",
      "2026-T1",
      "2025-AN",
      "2025-T3",
      "2025-T2",
      "2025-T1",
    ]);
  });

  it("étend automatiquement le sélecteur aux périodes historiques communes", () => {
    const reference = dataset.observations[0]!;
    const period2022 = {
      ...reference.period,
      periodId: "2022-T1",
      year: 2022,
      endDate: "2022-03-31",
      label: "T1 2022",
    };
    const historicalDataset = {
      ...dataset,
      periods: [...dataset.periods, period2022],
      observations: [
        ...dataset.observations,
        {
          ...reference,
          id: "MFC-2022-T1-core-eps",
          period: period2022,
        },
        {
          ...reference,
          id: "SLF-2022-T1-core-eps",
          companyId: "SLF" as const,
          period: period2022,
        },
      ],
    };

    expect(
      availablePeriods(historicalDataset).map((item) => item.periodId),
    ).toContain("2022-T1");
  });

  it("masque une ancienne période qui n’est pas commune aux compagnies", () => {
    const reference = dataset.observations[0]!;
    const oldPartialPeriod = {
      ...reference.period,
      periodId: "2024-T1",
      year: 2024,
      endDate: "2024-03-31",
      label: "T1 2024",
    };
    const oldPartialDataset = {
      ...dataset,
      periods: [...dataset.periods, oldPartialPeriod],
      observations: [
        ...dataset.observations,
        {
          ...reference,
          id: "MFC-2024-T1-core-eps",
          period: oldPartialPeriod,
        },
      ],
    };

    expect(
      availablePeriods(oldPartialDataset).map((item) => item.periodId),
    ).not.toContain("2024-T1");
  });

  it("ne mélange jamais deux années portant la même clé de période", () => {
    const state = initialState(dataset);
    const selected = state.dataset.observations.filter(
      (item) =>
        item.companyId === state.companyId &&
        item.period.periodId === state.periodId,
    );
    expect(selected).toHaveLength(1);
    expect(selected[0]?.period.periodId).toBe("2026-T2");
    expect(selected[0]?.comparison.periodId).toBe("2025-T2");
  });

  it("filtre les actualités avant rendu", () => {
    const container = document.createElement("div");
    renderNews(
      container,
      dataset.news.filter((item) => item.categories.includes("regulation")),
    );
    expect(container.textContent).toContain("Aucune actualité");
  });

  it("affiche une actualité T3 même si les derniers résultats sont T2", () => {
    document.body.innerHTML = `
      <div id="company-header"></div><div id="metrics"></div><div id="news"></div>
      <p id="news-freshness"></p>
      <section id="company-panel"></section>`;
    const state = initialState(dataset);
    expect(state.periodId).toBe("2026-T2");
    renderDashboard(state);
    expect(document.querySelector("#news")?.textContent).toContain(
      "Actualité postérieure aux derniers résultats",
    );
    expect(document.querySelector("#news-freshness")?.textContent).toContain(
      "15 juill. 2026",
    );
  });

  it("affiche qualité, sources en erreur et données périmées", () => {
    const container = document.createElement("div");
    renderStatus(
      container,
      {
        ...manifest,
        mode: "offline",
        lastAttemptAt: "2026-07-10T12:00:00Z",
        lastSuccessfulRefresh: "2026-06-01T00:00:00Z",
      },
      {
        ...quality,
        status: "partial",
        sourcesFailed: 1,
        sourceResults: [
          {
            sourceId: "mfc-results",
            companyId: "MFC",
            status: "failed",
            documentsDiscovered: 0,
            documentUrls: [],
            periodIds: [],
            message: "Source inaccessible",
            llmCalls: 0,
          },
          {
            sourceId: "slf-results",
            companyId: "SLF",
            status: "warning",
            documentsDiscovered: 1,
            documentUrls: ["https://example.com/slf"],
            periodIds: ["2026-T1"],
            message: "Extraction partielle",
            llmCalls: 1,
          },
          {
            sourceId: "gwo-official-news",
            companyId: "GWO",
            status: "warning",
            documentsDiscovered: 0,
            documentUrls: [],
            periodIds: [],
            message: "Aucun document",
            llmCalls: 0,
          },
        ],
      },
      new Date("2026-07-11T00:00:00Z"),
    );
    expect(container.textContent).toContain("Données anciennes");
    expect(container.textContent).toContain(
      "Données financières publiées avec réserves",
    );
    expect(container.textContent).toContain("Dernière tentative");
    expect(container.textContent).toContain(
      "Dernier rafraîchissement financier réussi",
    );
    expect(container.textContent).toContain("Mode : offline (hors ligne)");
    expect(container.textContent).toContain("1 source financière bloquée");
    expect(container.textContent).toContain(
      "1 source financière avec avertissement",
    );
    expect(container.textContent).toContain(
      "Actualités : 1 source avec avertissement",
    );
    expect(container.textContent).not.toContain("source(s) en erreur");
    expect(container.textContent).toContain("document plus récent non intégré");
    renderStatus(container, manifest, quality);
    expect(container.textContent).toContain("Mode : live (en ligne)");
  });

  it("ne dégrade pas les données financières pour un avertissement d’actualités", () => {
    const container = document.createElement("div");
    renderStatus(
      container,
      {
        ...manifest,
        companyFreshness: manifest.companyFreshness.map((item) => ({
          ...item,
          freshnessStatus: "current",
        })),
      },
      {
        ...quality,
        status: "partial",
        warnings: [
          {
            code: "no_documents_discovered",
            message: "Aucun document d’actualité découvert.",
            sourceId: "gwo-official-news",
          },
        ],
        sourceResults: [
          {
            sourceId: "mfc-results",
            companyId: "MFC",
            status: "success",
            documentsDiscovered: 1,
            documentUrls: ["https://example.com/mfc"],
            periodIds: ["2026-T1"],
            message: null,
            llmCalls: 0,
          },
          {
            sourceId: "gwo-official-news",
            companyId: "GWO",
            status: "warning",
            documentsDiscovered: 0,
            documentUrls: [],
            periodIds: [],
            message: "Aucun document",
            llmCalls: 0,
          },
        ],
      },
    );

    expect(container.textContent).toContain("Données financières validées");
    expect(container.textContent).toContain(
      "Actualités : 1 source avec avertissement",
    );
    expect(container.textContent).not.toContain(
      "Données financières publiées avec réserves",
    );
    expect(container.className).toContain("status-success");
  });

  it("navigue entre les onglets au clavier", () => {
    const container = document.createElement("div");
    document.body.append(container);
    renderCompanyTabs(container, dataset, "MFC", vi.fn());
    enableArrowNavigation(container);
    const buttons = container.querySelectorAll("button");
    buttons[0]?.focus();
    buttons[0]?.dispatchEvent(
      new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
    );
    expect(document.activeElement).toBe(buttons[1]);
  });

  it("trace uniquement l’historique trimestriel des compagnies", () => {
    const container = document.createElement("div");
    renderHistory(container, dataset, "metric:core_eps", "2025-AN");

    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelectorAll(".history-line")).toHaveLength(2);
    expect(container.textContent).toContain("Manuvie");
    expect(container.textContent).toContain("Sun Life");
    expect(container.textContent).toContain("T3 2025");
    expect(container.textContent).not.toContain("T1 2026");
    expect(
      [...container.querySelectorAll(".history-axis-label")].map(
        (label) => label.textContent,
      ),
    ).not.toContain("Annuel 2025");
  });

  it("borne l’historique à la période sélectionnée", () => {
    const container = document.createElement("div");

    renderHistory(container, dataset, "metric:core_eps", "2025-T2");

    expect(container.textContent).toContain("jusqu’à T2 2025");
    expect(container.textContent).toContain("T2 2025");
    expect(container.textContent).not.toContain("T3 2025");
    expect(container.textContent).not.toContain("T1 2026");
  });

  it("conserve une fenêtre historique de cinq années civiles", () => {
    const reference = dataset.observations[0]!;
    const period2021 = {
      ...reference.period,
      periodId: "2021-T1",
      year: 2021,
      endDate: "2021-03-31",
      label: "T1 2021",
    };
    const period2022 = {
      ...reference.period,
      periodId: "2022-T1",
      year: 2022,
      endDate: "2022-03-31",
      label: "T1 2022",
    };
    const historicalDataset = {
      ...dataset,
      periods: [...dataset.periods, period2021, period2022],
      observations: [
        ...dataset.observations,
        {
          ...reference,
          id: "MFC-2021-T1-core-eps",
          period: period2021,
        },
        {
          ...reference,
          id: "MFC-2022-T1-core-eps",
          period: period2022,
        },
      ],
    };
    const container = document.createElement("div");

    renderHistory(container, historicalDataset, "metric:core_eps", "2026-T2");

    expect(container.querySelector("svg")?.textContent).toContain("T1 2022");
    expect(container.querySelector("svg")?.textContent).not.toContain(
      "T1 2021",
    );
    expect(container.textContent).toContain("Fenêtre glissante de cinq ans");
  });

  it("permet de basculer l’historique vers la croissance du BPA", () => {
    const container = document.createElement("div");
    renderHistory(container, dataset, "growth:core_eps", "2025-AN");

    expect(
      container.querySelector("#history-chart-title")?.textContent,
    ).toContain("Variation annuelle");
    expect(container.querySelector("svg")?.textContent).toContain("%");
  });

  it("propose tous les KPI trimestriels publiés dans la liste historique", () => {
    const reference = dataset.observations[0]!;
    const richerDataset = {
      ...dataset,
      observations: [
        ...dataset.observations,
        {
          ...reference,
          id: "MFC-2025-T1-net-income",
          metricId: "net_income",
          label: "Résultat net",
          value: 1.2,
          unit: "CAD_BILLION",
          displayValue: "1,2 G$",
        },
        {
          ...reference,
          id: "MFC-2025-T1-core-roe",
          metricId: "core_roe",
          label: "Rendement des capitaux propres de base",
          value: 16.5,
          unit: "PERCENT",
          displayValue: "16,5 %",
          comparison: {
            ...reference.comparison,
            change: 0.9,
            changeUnit: "PERCENTAGE_POINT" as const,
            displayChange: "+0,9 pp",
          },
        },
        {
          ...reference,
          id: "MFC-2025-T1-licat",
          metricId: "licat_ratio",
          label: "Ratio LICAT",
          value: 138,
          unit: "PERCENT",
          displayValue: "138 %",
          comparison: {
            ...reference.comparison,
            change: -1,
            changeUnit: "PERCENTAGE_POINT" as const,
            displayChange: "−1 pp",
          },
        },
      ],
    };
    const values = historicalKpiOptions(richerDataset)
      .filter((option) => option.group === "values")
      .map((option) => option.value);
    expect(values).toEqual([
      "metric:core_eps",
      "metric:net_income",
      "metric:licat_ratio",
      "metric:core_roe",
    ]);

    const select = document.createElement("select");
    const selected = populateHistoricalKpiSelect(
      select,
      richerDataset,
      "metric:net_income",
    );
    expect(selected).toBe("metric:net_income");
    expect(select.value).toBe("metric:net_income");
    expect(select.querySelectorAll('option[value^="metric:"]')).toHaveLength(4);
    expect(select.textContent).toContain("Résultat net");
    expect(select.textContent).toContain("Ratio LICAT");
    expect(select.textContent).toContain(
      "Rendement des capitaux propres de base",
    );
  });

  it("normalise les millions en milliards pour un même KPI", () => {
    const mfc = dataset.observations[0]!;
    const slf = dataset.observations.find(
      (observation) => observation.companyId === "SLF",
    )!;
    const mixedUnitsDataset = {
      ...dataset,
      observations: [
        {
          ...mfc,
          id: "MFC-2025-T1-net-income",
          metricId: "net_income",
          label: "Résultat net",
          value: 1.2,
          unit: "CAD_BILLION",
          displayValue: "1,2 G$",
        },
        {
          ...slf,
          id: "SLF-2025-T1-net-income",
          metricId: "net_income",
          label: "Résultat net",
          value: 850,
          unit: "CAD_MILLION",
          displayValue: "850 M$",
        },
      ],
    };
    const container = document.createElement("div");
    renderHistory(container, mixedUnitsDataset, "metric:net_income", "2025-AN");

    expect(container.querySelectorAll(".history-line")).toHaveLength(2);
    const markerLabels = [
      ...container.querySelectorAll(".history-marker title"),
    ]
      .map((title) => title.textContent)
      .join(" ");
    expect(markerLabels).toContain("1,2 G$");
    expect(markerLabels).toContain("0,85 G$");
  });
});
