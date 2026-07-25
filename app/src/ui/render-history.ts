import type {
  Company,
  Observation,
  Period,
  VigieDataset,
} from "../domain/models";
import type { HistoricalKpi } from "./state";
import { clear, element } from "./dom";

const SVG_NS = "http://www.w3.org/2000/svg";
const WIDTH = 1100;
const HEIGHT = 430;
const FRAME = { left: 76, right: 46, top: 28, bottom: 72 };
const MAX_PERIODS = 12;

interface HistoricalPoint {
  period: Period;
  value: number;
  displayValue: string;
}

interface HistoricalSeries {
  company: Company;
  points: Map<string, HistoricalPoint>;
}

function svgElement<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attributes: Record<string, string | number> = {},
): SVGElementTagNameMap[K] {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attributes)) {
    node.setAttribute(key, String(value));
  }
  return node;
}

function valueForObservation(
  observation: Observation,
  kpi: HistoricalKpi,
): HistoricalPoint | null {
  if (kpi === "core_eps") {
    return {
      period: observation.period,
      value: observation.value,
      displayValue: observation.displayValue,
    };
  }
  if (
    observation.comparison.change === null ||
    observation.comparison.changeUnit !== "PERCENT"
  ) {
    return null;
  }
  const value = observation.comparison.change * 100;
  return {
    period: observation.period,
    value,
    displayValue: `${new Intl.NumberFormat("fr-CA", {
      maximumFractionDigits: 1,
    }).format(value)} %`,
  };
}

function formatAxisValue(value: number, kpi: HistoricalKpi): string {
  const formatted = new Intl.NumberFormat("fr-CA", {
    minimumFractionDigits: kpi === "core_eps" ? 2 : 0,
    maximumFractionDigits: kpi === "core_eps" ? 2 : 1,
  }).format(value);
  return kpi === "core_eps" ? `${formatted} $` : `${formatted} %`;
}

function buildSeries(
  dataset: VigieDataset,
  kpi: HistoricalKpi,
): HistoricalSeries[] {
  return dataset.companies.map((company) => {
    const points = new Map<string, HistoricalPoint>();
    for (const observation of dataset.observations) {
      if (
        observation.companyId !== company.id ||
        observation.metricId !== "core_eps" ||
        observation.period.type !== "quarter"
      ) {
        continue;
      }
      const point = valueForObservation(observation, kpi);
      if (point) points.set(observation.period.periodId, point);
    }
    return { company, points };
  });
}

function markerForPoint(x: number, y: number, index: number): SVGElement {
  const className = `history-marker history-series-${index}`;
  if (index === 1) {
    return svgElement("rect", {
      x: x - 4.5,
      y: y - 4.5,
      width: 9,
      height: 9,
      class: className,
    });
  }
  if (index === 2) {
    return svgElement("polygon", {
      points: `${x},${y - 5} ${x + 5},${y + 4} ${x - 5},${y + 4}`,
      class: className,
    });
  }
  if (index === 3) {
    return svgElement("polygon", {
      points: `${x},${y - 5} ${x + 5},${y} ${x},${y + 5} ${x - 5},${y}`,
      class: className,
    });
  }
  return svgElement("circle", {
    cx: x,
    cy: y,
    r: 4.5,
    class: className,
  });
}

export function renderHistory(
  container: HTMLElement,
  dataset: VigieDataset,
  kpi: HistoricalKpi,
): void {
  clear(container);
  const series = buildSeries(dataset, kpi);
  const periodIds = new Set(series.flatMap((item) => [...item.points.keys()]));
  const periods = dataset.periods
    .filter(
      (period) => period.type === "quarter" && periodIds.has(period.periodId),
    )
    .sort((left, right) => left.endDate.localeCompare(right.endDate))
    .slice(-MAX_PERIODS);
  const values = series.flatMap((item) =>
    periods
      .map((period) => item.points.get(period.periodId)?.value)
      .filter((value): value is number => value !== undefined),
  );
  if (periods.length === 0 || values.length === 0) {
    container.append(
      element("p", {
        className: "empty-state",
        text: "Aucune donnée historique comparable n’est disponible.",
      }),
    );
    return;
  }

  const legend = element("ul", { className: "history-legend" });
  series.forEach((item, index) => {
    if (item.points.size === 0) return;
    const entry = element("li");
    entry.append(
      element("span", {
        className: `history-legend-mark history-series-${index}`,
      }),
      element("span", { text: item.company.name }),
    );
    legend.append(entry);
  });

  const svg = svgElement("svg", {
    class: "history-chart",
    viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
    role: "img",
    "aria-labelledby": "history-chart-title history-chart-description",
  });
  const title = svgElement("title", { id: "history-chart-title" });
  title.textContent =
    kpi === "core_eps"
      ? "Historique trimestriel du BPA de base"
      : "Historique trimestriel de la croissance du BPA de base";
  const description = svgElement("desc", {
    id: "history-chart-description",
  });
  description.textContent =
    "Comparaison des quatre assureurs. Une absence de point indique que la donnée n’est pas publiée.";
  svg.append(title, description);

  const plotWidth = WIDTH - FRAME.left - FRAME.right;
  const plotHeight = HEIGHT - FRAME.top - FRAME.bottom;
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const domainMin = kpi === "core_eps" ? 0 : Math.min(0, rawMin);
  const domainRange = Math.max(rawMax - domainMin, 1);
  const domainMax = rawMax + domainRange * 0.12;
  const x = (index: number): number =>
    FRAME.left +
    (periods.length === 1
      ? plotWidth / 2
      : (index / (periods.length - 1)) * plotWidth);
  const y = (value: number): number =>
    FRAME.top +
    plotHeight -
    ((value - domainMin) / (domainMax - domainMin)) * plotHeight;

  for (let index = 0; index <= 4; index += 1) {
    const value = domainMin + ((domainMax - domainMin) / 4) * index;
    const yPosition = y(value);
    svg.append(
      svgElement("line", {
        x1: FRAME.left,
        y1: yPosition,
        x2: WIDTH - FRAME.right,
        y2: yPosition,
        class: "history-grid-line",
      }),
    );
    const label = svgElement("text", {
      x: FRAME.left - 12,
      y: yPosition + 4,
      "text-anchor": "end",
      class: "history-axis-label",
    });
    label.textContent = formatAxisValue(value, kpi);
    svg.append(label);
  }

  periods.forEach((period, index) => {
    const label = svgElement("text", {
      x: x(index),
      y: HEIGHT - 30,
      "text-anchor": "middle",
      class: "history-axis-label",
    });
    label.textContent = period.label;
    svg.append(label);
  });

  series.forEach((item, seriesIndex) => {
    let path = "";
    let previousAvailable = false;
    const markers: SVGElement[] = [];
    periods.forEach((period, periodIndex) => {
      const point = item.points.get(period.periodId);
      if (!point) {
        previousAvailable = false;
        return;
      }
      const xPosition = x(periodIndex);
      const yPosition = y(point.value);
      path += `${previousAvailable ? " L" : " M"} ${xPosition} ${yPosition}`;
      previousAvailable = true;
      const marker = markerForPoint(xPosition, yPosition, seriesIndex);
      const markerTitle = svgElement("title");
      markerTitle.textContent = `${item.company.name} · ${period.label} · ${point.displayValue}`;
      marker.append(markerTitle);
      markers.push(marker);
    });
    if (path) {
      svg.append(
        svgElement("path", {
          d: path.trim(),
          class: `history-line history-series-${seriesIndex}`,
        }),
      );
    }
    svg.append(...markers);
  });

  const note = element("p", {
    className: "history-note",
    text: "Périodes trimestrielles seulement. Les interruptions indiquent des données non encore publiées.",
  });
  container.append(legend, svg, note);
}
