import type { CompanyId, Period, VigieDataset } from "../domain/models";
import { defaultHistoricalKpi, type HistoricalKpi } from "./history-kpis";

export type ViewMode = "summary" | "company" | "history" | "chat";
export type { HistoricalKpi } from "./history-kpis";

export interface AppState {
  dataset: VigieDataset;
  companyId: CompanyId;
  periodId: string | null;
  category: string;
  viewMode: ViewMode;
  historicalKpi: HistoricalKpi;
}

export function initialState(dataset: VigieDataset): AppState {
  const company = dataset.companies[0];
  if (!company) throw new Error("Le jeu de données est incomplet.");
  return {
    dataset,
    companyId: company.id,
    periodId: latestPeriodId(dataset),
    category: "all",
    viewMode: "summary",
    historicalKpi: defaultHistoricalKpi(dataset),
  };
}

export function availablePeriods(dataset: VigieDataset): Period[] {
  const companiesByPeriod = new Map<string, Set<CompanyId>>();
  for (const observation of dataset.observations) {
    const companies =
      companiesByPeriod.get(observation.period.periodId) ??
      new Set<CompanyId>();
    companies.add(observation.companyId);
    companiesByPeriod.set(observation.period.periodId, companies);
  }
  const publishedYears = dataset.periods
    .filter((period) => companiesByPeriod.has(period.periodId))
    .map((period) => period.year);
  const latestPublishedYear =
    publishedYears.length > 0 ? Math.max(...publishedYears) : null;
  return [...dataset.periods]
    .filter((period) => {
      const companies = companiesByPeriod.get(period.periodId);
      if (!companies || latestPublishedYear === null) return false;
      // L'année courante est publiée progressivement; les années antérieures
      // restent limitées aux périodes comparables pour tous les assureurs.
      return (
        period.year === latestPublishedYear ||
        dataset.companies.every((company) => companies.has(company.id))
      );
    })
    .sort((left, right) => right.endDate.localeCompare(left.endDate));
}

export function latestPeriodId(dataset: VigieDataset): string | null {
  return availablePeriods(dataset)[0]?.periodId ?? null;
}

export function availablePeriodsForCompany(
  dataset: VigieDataset,
  companyId: CompanyId,
): Period[] {
  const publishedIds = new Set(
    dataset.observations
      .filter((item) => item.companyId === companyId)
      .map((item) => item.period.periodId),
  );
  return [...dataset.periods]
    .filter((period) => publishedIds.has(period.periodId))
    .sort((left, right) => right.endDate.localeCompare(left.endDate));
}

export function latestPeriodIdForCompany(
  dataset: VigieDataset,
  companyId: CompanyId,
): string | null {
  return availablePeriodsForCompany(dataset, companyId)[0]?.periodId ?? null;
}

export function selectCompany(state: AppState, companyId: CompanyId): void {
  state.companyId = companyId;
}
