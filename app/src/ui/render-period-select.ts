import type { Period } from "../domain/models";
import { shortPeriod } from "../formatters/period";
import { clear, element } from "./dom";

export function renderPeriodSelect(
  container: HTMLElement,
  periods: Period[],
  activeId: string | null,
  onSelect: (periodId: string) => void,
): void {
  clear(container);
  const select = element("select", {
    className: "period-select",
  });
  select.id = "period-select";
  select.setAttribute("aria-label", "Choisir la période commune");
  for (const period of periods) {
    select.append(new Option(shortPeriod(period), period.periodId));
  }
  select.value = activeId ?? "";
  select.addEventListener("change", () => onSelect(select.value));
  container.append(select);
}
