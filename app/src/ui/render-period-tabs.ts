import type { Period } from "../domain/models";
import { shortPeriod } from "../formatters/period";
import { clear, element } from "./dom";

export function renderPeriodTabs(
  container: HTMLElement,
  periods: Period[],
  activeId: string | null,
  onSelect: (periodId: string) => void,
): void {
  clear(container);
  for (const period of periods) {
    const button = element("button", {
      className: "period-tab",
      text: shortPeriod(period),
    });
    button.type = "button";
    button.setAttribute("role", "tab");
    button.setAttribute("aria-controls", "company-panel");
    button.dataset.periodId = period.periodId;
    button.setAttribute("aria-selected", String(period.periodId === activeId));
    button.tabIndex = period.periodId === activeId ? 0 : -1;
    button.addEventListener("click", () => onSelect(period.periodId));
    container.append(button);
  }
}
