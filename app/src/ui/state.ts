import type { CompanyId, Period, VigieDataset } from "../domain/models";

export interface AppState {
  dataset: VigieDataset;
  companyId: CompanyId;
  periodId: string | null;
  category: string;
}

export function initialState(dataset: VigieDataset): AppState {
  const company = dataset.companies[0];
  if (!company) throw new Error("Le jeu de données est incomplet.");
  return {
    dataset,
    companyId: company.id,
    periodId: latestPeriodIdForCompany(dataset, company.id),
    category: "all",
  };
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
  state.periodId = latestPeriodIdForCompany(state.dataset, companyId);
}
