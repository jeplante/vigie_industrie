import { METRIC_CATALOG } from "../domain/metric-catalog";
import type { VigieDataset } from "../domain/models";

export type HistoricalKpiMode = "metric" | "growth";
export type HistoricalKpi = `${HistoricalKpiMode}:${string}`;

export interface HistoricalKpiOption {
  value: HistoricalKpi;
  label: string;
  group: "values" | "growth";
}

export interface HistoricalKpiSelection {
  mode: HistoricalKpiMode;
  metricId: string;
  label: string;
  unit: string;
}

function metricIdsInCatalogOrder(metricIds: Set<string>): string[] {
  const catalogIds = METRIC_CATALOG.map((metric) => metric.id).filter((id) =>
    metricIds.has(id),
  );
  const knownIds = new Set(catalogIds);
  const otherIds = [...metricIds]
    .filter((id) => !knownIds.has(id))
    .sort((left, right) => left.localeCompare(right, "fr-CA"));
  return [...catalogIds, ...otherIds];
}

export function historicalKpiOptions(
  dataset: VigieDataset,
): HistoricalKpiOption[] {
  const quarterly = dataset.observations.filter(
    (observation) => observation.period.type === "quarter",
  );
  const metricIds = new Set(
    quarterly.map((observation) => observation.metricId),
  );
  const orderedIds = metricIdsInCatalogOrder(metricIds);
  const values = orderedIds.map((metricId): HistoricalKpiOption => {
    const definition = METRIC_CATALOG.find((metric) => metric.id === metricId);
    const observation = quarterly.find((item) => item.metricId === metricId);
    return {
      value: `metric:${metricId}`,
      label: definition?.label ?? observation?.label ?? metricId,
      group: "values",
    };
  });
  const growth = orderedIds
    .filter((metricId) =>
      quarterly.some(
        (observation) =>
          observation.metricId === metricId &&
          observation.comparison.change !== null &&
          observation.comparison.changeUnit === "PERCENT",
      ),
    )
    .map((metricId): HistoricalKpiOption => {
      const definition = METRIC_CATALOG.find(
        (metric) => metric.id === metricId,
      );
      const observation = quarterly.find((item) => item.metricId === metricId);
      const label = definition?.label ?? observation?.label ?? metricId;
      return {
        value: `growth:${metricId}`,
        label: `Variation annuelle — ${label}`,
        group: "growth",
      };
    });
  return [...values, ...growth];
}

export function defaultHistoricalKpi(dataset: VigieDataset): HistoricalKpi {
  const options = historicalKpiOptions(dataset);
  return (
    options.find((option) => option.value === "metric:core_eps")?.value ??
    options[0]?.value ??
    "metric:core_eps"
  );
}

export function parseHistoricalKpi(
  dataset: VigieDataset,
  value: HistoricalKpi,
): HistoricalKpiSelection {
  const separator = value.indexOf(":");
  const mode = value.slice(0, separator) as HistoricalKpiMode;
  const metricId = value.slice(separator + 1);
  const definition = METRIC_CATALOG.find((metric) => metric.id === metricId);
  const observation = dataset.observations.find(
    (item) => item.metricId === metricId,
  );
  return {
    mode,
    metricId,
    label: definition?.label ?? observation?.label ?? metricId,
    unit: definition?.unit ?? observation?.unit ?? "",
  };
}

export function populateHistoricalKpiSelect(
  select: HTMLSelectElement,
  dataset: VigieDataset,
  selected: HistoricalKpi,
): HistoricalKpi {
  const options = historicalKpiOptions(dataset);
  const selectedValue = options.some((option) => option.value === selected)
    ? selected
    : defaultHistoricalKpi(dataset);
  const valuesGroup = document.createElement("optgroup");
  valuesGroup.label = "Valeurs publiées";
  const growthGroup = document.createElement("optgroup");
  growthGroup.label = "Variations annuelles";

  for (const option of options) {
    const node = new Option(option.label, option.value);
    (option.group === "values" ? valuesGroup : growthGroup).append(node);
  }

  select.replaceChildren(valuesGroup);
  if (growthGroup.childElementCount > 0) select.append(growthGroup);
  select.value = selectedValue;
  return selectedValue;
}
