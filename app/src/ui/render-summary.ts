import { METRIC_CATALOG } from "../domain/metric-catalog";
import type { CompanyId, Observation, VigieDataset } from "../domain/models";
import { clear, element } from "./dom";

const ARROW = { up: "▲", down: "▼", neutral: "◆" } as const;
const METRIC_ORDER = new Map(
  METRIC_CATALOG.map((metric, index) => [metric.id, index]),
);

function summaryMetricIds(observations: Observation[]): string[] {
  return [
    ...new Set(observations.map((observation) => observation.metricId)),
  ].sort((left, right) => {
    const leftOrder = METRIC_ORDER.get(left) ?? Number.MAX_SAFE_INTEGER;
    const rightOrder = METRIC_ORDER.get(right) ?? Number.MAX_SAFE_INTEGER;
    return leftOrder - rightOrder || left.localeCompare(right, "fr-CA");
  });
}

function metricLabel(metricId: string, observations: Observation[]): string {
  return (
    METRIC_CATALOG.find((metric) => metric.id === metricId)?.label ??
    observations.find((observation) => observation.metricId === metricId)
      ?.label ??
    metricId
  );
}

function metricCell(
  observation: Observation | undefined,
): HTMLTableCellElement {
  const cell = element("td", { className: "summary-metric-cell" });
  if (!observation) {
    cell.classList.add("summary-metric-missing");
    cell.append(
      element("span", {
        text: "—",
        className: "summary-metric-empty",
      }),
    );
    cell.title = "Donnée non publiée pour cette compagnie.";
    return cell;
  }

  const source = element("a", {
    className: "summary-metric-value",
    text: observation.displayValue,
  });
  source.href = observation.source.url;
  source.target = "_blank";
  source.rel = "noopener noreferrer";
  source.title = `Source : ${observation.source.title}`;

  const comparison = element("span", {
    className: "summary-metric-comparison",
    text: observation.comparison.periodLabel
      ? `vs ${observation.comparison.periodLabel}`
      : "Sans comparatif",
  });
  const delta = element("span", {
    className: `delta delta-${observation.direction}`,
    text: `${ARROW[observation.direction]} ${observation.comparison.displayChange}`,
  });
  cell.append(source, comparison, delta);
  return cell;
}

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

  const periodObservations = dataset.observations.filter(
    (observation) => observation.period.periodId === periodId,
  );
  const metricIds = summaryMetricIds(periodObservations);
  const wrapper = element("div", { className: "summary-table-wrap" });
  const table = element("table", { className: "summary-table" });
  const caption = element("caption", {
    className: "visually-hidden",
    text: `Synthèse des assureurs pour ${period.label}`,
  });
  const head = element("thead");
  const headingRow = element("tr");
  const companyHeading = element("th", { text: "Compagnie" });
  companyHeading.scope = "col";
  headingRow.append(companyHeading);
  for (const metricId of metricIds) {
    const heading = element("th", {
      text: metricLabel(metricId, periodObservations),
    });
    heading.scope = "col";
    headingRow.append(heading);
  }
  head.append(headingRow);

  const body = element("tbody");
  for (const company of dataset.companies) {
    const companyObservations = periodObservations.filter(
      (observation) => observation.companyId === company.id,
    );
    const observationsByMetric = new Map(
      companyObservations.map((observation) => [
        observation.metricId,
        observation,
      ]),
    );
    const row = element("tr", {
      className: `summary-company-row summary-company-${String(company.id).toLowerCase()}`,
    });
    const companyCell = element("th", { className: "summary-company-cell" });
    companyCell.scope = "row";
    const companyName = element("span", {
      className: "summary-company-name",
      text: company.name,
    });
    const ticker = element("span", {
      className: "summary-company-ticker",
      text: company.ticker,
    });
    const detailButton = element("button", {
      className: "summary-company-detail",
      text: "Détail",
    });
    detailButton.type = "button";
    detailButton.addEventListener("click", () => onSelectCompany(company.id));
    companyCell.append(companyName, ticker);
    if (companyObservations.length === 0) {
      companyCell.append(
        element("span", {
          className: "summary-company-unavailable",
          text: "Données non encore publiées",
        }),
      );
    }
    companyCell.append(detailButton);
    row.append(companyCell);
    for (const metricId of metricIds) {
      row.append(metricCell(observationsByMetric.get(metricId)));
    }
    body.append(row);
  }
  table.append(caption, head, body);
  wrapper.append(table);
  container.append(wrapper);
}
