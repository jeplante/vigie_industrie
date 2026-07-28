import "./styles.css";
import { StaticJsonDataProvider } from "./data/StaticJsonDataProvider";
import type { DataProvider } from "./data/DataProvider";
import type { AppState, ViewMode } from "./ui/state";
import { availablePeriods, initialState, selectCompany } from "./ui/state";
import { requiredElement } from "./ui/dom";
import { renderCompanyTabs } from "./ui/render-company-tabs";
import { renderPeriodSelect } from "./ui/render-period-select";
import { renderDashboard } from "./ui/render-dashboard";
import { renderStatus } from "./ui/render-status";
import { enableArrowNavigation } from "./ui/accessibility";
import { downloadCsv } from "./export/export-csv";
import { renderHistory } from "./ui/render-history";
import {
  populateHistoricalKpiSelect,
  type HistoricalKpi,
} from "./ui/history-kpis";
import { renderSummary } from "./ui/render-summary";

export class VigieApp {
  private state: AppState | null = null;

  public constructor(private readonly provider: DataProvider) {}

  public async start(): Promise<void> {
    const status = requiredElement("status");
    const errorPanel = requiredElement("load-error");
    status.hidden = false;
    status.setAttribute("aria-busy", "true");
    errorPanel.hidden = true;
    try {
      const [dataset, manifest, report] = await Promise.all([
        this.provider.loadDataset(),
        this.provider.loadManifest(),
        this.provider.loadQualityReport(),
      ]);
      this.state = initialState(dataset);
      renderStatus(status, manifest, report);
      requiredElement("app-content").hidden = false;
      this.bindControls();
      this.render();
    } catch (error) {
      status.hidden = true;
      requiredElement("app-content").hidden = true;
      errorPanel.hidden = false;
      requiredElement("load-error-message").textContent =
        error instanceof Error
          ? error.message
          : "Une erreur inconnue est survenue.";
    }
  }

  private bindControls(): void {
    const category = requiredElement<HTMLSelectElement>("news-category");
    category.replaceChildren(new Option("Toutes", "all"));
    const categories = [
      ...new Set(
        this.state?.dataset.news.flatMap((item) => item.categories) ?? [],
      ),
    ].sort();
    for (const item of categories)
      category.append(new Option(item.replaceAll("_", " "), item));
    category.onchange = () => {
      if (!this.state) return;
      this.state.category = category.value;
      this.render();
    };
    requiredElement<HTMLButtonElement>("export-csv").onclick = () => {
      if (this.state) downloadCsv(this.state.dataset);
    };
    for (const button of requiredElement(
      "view-tabs",
    ).querySelectorAll<HTMLButtonElement>("[data-view]")) {
      button.onclick = () => {
        if (!this.state) return;
        this.state.viewMode = button.dataset.view as ViewMode;
        this.render();
      };
    }
    const historicalKpi = requiredElement<HTMLSelectElement>("history-kpi");
    if (this.state) {
      this.state.historicalKpi = populateHistoricalKpiSelect(
        historicalKpi,
        this.state.dataset,
        this.state.historicalKpi,
      );
    }
    historicalKpi.onchange = () => {
      if (!this.state) return;
      this.state.historicalKpi = historicalKpi.value as HistoricalKpi;
      this.render();
    };
  }

  private render(): void {
    if (!this.state) return;
    const summaryView = requiredElement("summary-view");
    const companyView = requiredElement("company-view");
    const historyView = requiredElement("history-view");
    const isSummary = this.state.viewMode === "summary";
    summaryView.hidden = !isSummary;
    companyView.hidden = this.state.viewMode !== "company";
    historyView.hidden = this.state.viewMode !== "history";
    for (const button of requiredElement(
      "view-tabs",
    ).querySelectorAll<HTMLButtonElement>("[data-view]")) {
      const selected = button.dataset.view === this.state.viewMode;
      button.setAttribute("aria-selected", String(selected));
      button.tabIndex = selected ? 0 : -1;
    }
    const historicalKpi = requiredElement<HTMLSelectElement>("history-kpi");
    historicalKpi.value = this.state.historicalKpi;

    const companyTabs = requiredElement("company-tabs");
    renderPeriodSelect(
      requiredElement("period-selector"),
      availablePeriods(this.state.dataset),
      this.state.periodId,
      (periodId) => {
        if (!this.state) return;
        this.state.periodId = periodId;
        this.render();
      },
    );
    renderSummary(
      requiredElement("company-summary"),
      this.state.dataset,
      this.state.periodId,
      (companyId) => {
        if (!this.state) return;
        selectCompany(this.state, companyId);
        this.state.viewMode = "company";
        this.render();
      },
    );
    renderCompanyTabs(
      companyTabs,
      this.state.dataset,
      this.state.companyId,
      (companyId) => {
        if (!this.state) return;
        selectCompany(this.state, companyId);
        this.render();
      },
    );
    renderDashboard(this.state);
    renderHistory(
      requiredElement("history-chart"),
      this.state.dataset,
      this.state.historicalKpi,
      this.state.periodId,
    );
  }
}

const app = new VigieApp(new StaticJsonDataProvider());
enableArrowNavigation(requiredElement("view-tabs"));
enableArrowNavigation(requiredElement("company-tabs"));
requiredElement<HTMLButtonElement>("retry-load").addEventListener(
  "click",
  () => void app.start(),
);
void app.start();
