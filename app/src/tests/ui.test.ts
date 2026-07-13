import { describe, expect, it, vi } from "vitest";
import { enableArrowNavigation } from "../ui/accessibility";
import { renderCompanyTabs } from "../ui/render-company-tabs";
import { renderPeriodTabs } from "../ui/render-period-tabs";
import { renderNews } from "../ui/render-news";
import { renderDashboard } from "../ui/render-dashboard";
import { renderStatus } from "../ui/render-status";
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
      { ...quality, status: "partial", sourcesFailed: 1 },
      new Date("2026-07-11T00:00:00Z"),
    );
    expect(container.textContent).toContain("Données anciennes");
    expect(container.textContent).toContain("Dernière tentative");
    expect(container.textContent).toContain(
      "Dernier rafraîchissement financier réussi",
    );
    expect(container.textContent).toContain("Mode : offline (hors ligne)");
    expect(container.textContent).toContain("1 source");
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
});
