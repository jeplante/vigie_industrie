export type HistoricalBasis = "qtd" | "ytd";

const ADDITIVE_METRICS = new Set(["core_eps", "core_earnings", "net_income"]);

export function isAdditiveHistoricalMetric(metricId: string): boolean {
  return ADDITIVE_METRICS.has(metricId);
}
