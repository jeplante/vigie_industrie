import type { CompanyId, PeriodKey, VigieDataset } from '../domain/models';

export interface AppState {
  dataset: VigieDataset;
  companyId: CompanyId;
  periodKey: PeriodKey;
  category: string;
}

export function initialState(dataset: VigieDataset): AppState {
  const company = dataset.companies[0];
  const period = dataset.periods[0];
  if (!company || !period) throw new Error('Le jeu de données est incomplet.');
  return { dataset, companyId: company.id, periodKey: period.key, category: 'all' };
}
