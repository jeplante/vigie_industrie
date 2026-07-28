import type { CompanyId, VigieDataset } from "../domain/models";
import { renderMetrics } from "./render-metrics";
import { clear, element } from "./dom";

export function renderSummary(
  container: HTMLElement,
  dataset: VigieDataset,
  periodId: string | null,
  onSelectCompany: (companyId: CompanyId) => void,
): void {
  clear(container);
  const period = dataset.periods.find((item) => item.periodId === periodId);
  if (!period) {
    container.append(
      element("p", {
        className: "empty-state",
        text: "Aucune période publiée n’est disponible.",
      }),
    );
    return;
  }

  for (const company of dataset.companies) {
    const section = element("section", {
      className: `company-summary-row company-summary-${String(company.id).toLowerCase()}`,
    });
    section.setAttribute("aria-labelledby", `summary-company-${company.id}`);

    const heading = element("div", { className: "company-summary-heading" });
    const title = element("div");
    title.append(
      element("p", {
        className: "company-summary-ticker",
        text: company.ticker,
      }),
      element("h3", {
        text: `${company.name} · ${period.label}`,
      }),
    );
    title.querySelector("h3")!.id = `summary-company-${company.id}`;

    const detailButton = element("button", {
      className: "button company-summary-detail",
      text: "Voir le détail",
    });
    detailButton.type = "button";
    detailButton.addEventListener("click", () => onSelectCompany(company.id));
    heading.append(title, detailButton);

    const metrics = element("div", { className: "metrics-grid" });
    renderMetrics(
      metrics,
      dataset.observations.filter(
        (observation) =>
          observation.companyId === company.id &&
          observation.period.periodId === periodId,
      ),
    );
    section.append(heading, metrics);
    container.append(section);
  }
}
