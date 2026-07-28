import { METRIC_CATALOG } from "./metric-catalog";
import type { Observation } from "./models";

function searchableMetricText(observation: Observation): string {
  return `${observation.label} ${observation.note}`
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

export function canonicalMetricId(observation: Observation): string {
  if (observation.metricId === "solvency_ratio") return "licat_ratio";
  if (
    observation.metricId === "net_income" &&
    /\b(underlying|sous-jacent|core earnings|activites de base)\b/u.test(
      searchableMetricText(observation),
    )
  ) {
    return "core_earnings";
  }
  return observation.metricId;
}

export function canonicalMetricLabel(observation: Observation): string {
  const metricId = canonicalMetricId(observation);
  return (
    METRIC_CATALOG.find((metric) => metric.id === metricId)?.label ??
    observation.label
  );
}

export function canonicalObservations(
  observations: Observation[],
): Observation[] {
  const byMetric = new Map<string, Observation>();
  for (const observation of observations) {
    const metricId = canonicalMetricId(observation);
    const current = byMetric.get(metricId);
    if (
      current === undefined ||
      (observation.metricId === metricId && current.metricId !== metricId)
    ) {
      byMetric.set(metricId, observation);
    }
  }
  return [...byMetric.values()];
}
