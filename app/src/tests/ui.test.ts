import { describe, expect, it, vi } from "vitest";
import { enableArrowNavigation } from "../ui/accessibility";
import { renderCompanyTabs } from "../ui/render-company-tabs";
import { renderPeriodTabs } from "../ui/render-period-tabs";
import { renderNews } from "../ui/render-news";
import { renderDashboard } from "../ui/render-dashboard";
import { renderHistory } from "../ui/render-history";
import { renderStatus } from "../ui/render-status";
import {
  historicalKpiOptions,
  populateHistoricalKpiSelect,
} from "../ui/history-kpis";
import {
  availablePeriodsForCompany,
  initialState,
  selectCompany,
} from "../ui/state";
import { dataset, manifest, quality } from "./fixtures";

describe("interface", () => {
  it("change de compagnie et de période", () => {
    const companies = document.createElement("div");
    const periods = document.createElement("div");
    const onCompany = vi.fn();
    const onPeriod = vi.fn();
    renderCompanyTabs(companies, dataset, "MFC", onCompany);
    renderPeriodTabs(
      periods,
      availablePeriodsForCompany(dataset, "MFC"),
      "2026-T2",
      onPeriod,
    );
    companies.querySelectorAll("button")[1]?.click();
    periods.querySelectorAll("button")[1]?.click();
    expect(onCompany).toHaveBeenCalledWith("SLF");
    expect(onPeriod).toHaveBeenCalledWith("2026-T1");
  });

  it("sélectionne la période la plus récente propre à chaque compagnie", () => {
    const state = initialState(dataset);
    expect(state.periodId).toBe("2026-T2");
    expect(state.viewMode).toBe("summary");
    expect(state.historicalKpi).toBe("metric:core_eps");
    selectCompany(state, "SLF");
    expect(state.periodId).toBe("2025-AN");
    expect(
      availablePeriodsForCompany(dataset, "SLF").map((item) => item.periodId),
    ).toEqual(["2025-AN", "2025-T3", "2025-T2", "2025-T1"]);
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
      <section id="company-panel"></section>`;
    const state = initialState(dataset);
    expect(state.periodId).toBe("2026-T2");
    renderDashboard(state);
    expect(document.querySelector("#news")?.textContent).toContain(
      "Actualité postérieure aux derniers résultats",
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
            anthropicCalls: 0,
          },
          {
            sourceId: "slf-results",
            companyId: "SLF",
            status: "warning",
            documentsDiscovered: 1,
            documentUrls: ["https://example.com/slf"],
            periodIds: ["2026-T1"],
            message: "Extraction partielle",
            anthropicCalls: 1,
          },
          {
            sourceId: "gwo-official-news",
            companyId: "GWO",
            status: "warning",
            documentsDiscovered: 0,
            documentUrls: [],
            periodIds: [],
            message: "Aucun document",
            anthropicCalls: 0,
          },
        ],
      },
      new Date("2026-07-11T00:00:00Z"),
    );
    expect(container.textContent).toContain("Données anciennes");
    expect(container.textContent).toContain("Données publiées avec réserves");
    expect(container.textContent).toContain("Dernière tentative");
    expect(container.textContent).toContain(
      "Dernier rafraîchissement financier réussi",
    );
    expect(container.textContent).toContain("Mode : offline (hors ligne)");
    expect(container.textContent).toContain("1 source bloquée");
    expect(container.textContent).toContain("2 sources avec avertissement");
    expect(container.textContent).not.toContain("source(s) en erreur");
    expect(container.textContent).toContain("document plus récent non intégré");
    renderStatus(container, manifest, quality);
    expect(container.textContent).toContain("Mode : live (en ligne)");
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
    renderHistory(container, dataset, "metric:core_eps");

    expect(container.querySelector("svg")).not.toBeNull();
    expect(container.querySelectorAll(".history-line")).toHaveLength(2);
    expect(container.textContent).toContain("Manuvie");
    expect(container.textContent).toContain("Sun Life");
    expect(container.textContent).toContain("T2 2026");
    expect(container.textContent).not.toContain("Annuel 2025");
  });

  it("permet de basculer l’historique vers la croissance du BPA", () => {
    const container = document.createElement("div");
    renderHistory(container, dataset, "growth:core_eps");

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
    ]);

    const select = document.createElement("select");
    const selected = populateHistoricalKpiSelect(
      select,
      richerDataset,
      "metric:net_income",
    );
    expect(selected).toBe("metric:net_income");
    expect(select.value).toBe("metric:net_income");
    expect(select.querySelectorAll('option[value^="metric:"]')).toHaveLength(3);
    expect(select.textContent).toContain("Résultat net");
    expect(select.textContent).toContain("Ratio LICAT");
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
    renderHistory(container, mixedUnitsDataset, "metric:net_income");

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
