import type { Observation } from "../domain/models";
import { clear, element } from "./dom";

const ARROW = { up: "▲", down: "▼", neutral: "◆" } as const;

export function renderMetrics(
  container: HTMLElement,
  observations: Observation[],
): void {
  clear(container);
  if (observations.length === 0) {
    container.append(
      element("p", {
        className: "empty-state",
        text: "Données non encore publiées.",
      }),
    );
    return;
  }
  for (const observation of observations) {
    const card = element("article", { className: "metric-card" });
    card.append(element("h3", { text: observation.label }));
    card.append(
      element("p", {
        className: "metric-value",
        text: observation.displayValue,
      }),
    );
    const comparison = element("p", { className: "metric-comparison" });
    comparison.append(
      element("span", {
        text: `Comparatif : ${observation.comparison.displayValue}`,
      }),
      element("span", {
        className: `delta delta-${observation.direction}`,
        text: `${ARROW[observation.direction]} ${observation.comparison.displayChange}`,
      }),
    );
    card.append(comparison);
    card.append(
      element("p", { className: "metric-note", text: observation.note }),
    );
    const source = element("a", {
      className: "metric-source",
      text: `Source : ${observation.source.title}`,
    });
    source.href = observation.source.url;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    card.append(source);
    container.append(card);
  }
}
