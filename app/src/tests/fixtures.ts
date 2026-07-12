import type { DatasetManifest, QualityReport, VigieDataset } from '../domain/models';

export const dataset: VigieDataset = {
  schemaVersion: '2.0.0',
  generatedAt: '2026-07-10T12:00:00Z',
  companies: [
    { id: 'MFC', name: 'Manuvie', fullName: 'Manuvie', ticker: 'MFC.TO', investorRelationsUrl: 'https://example.com/mfc' },
    { id: 'SLF', name: 'Sun Life', fullName: 'Sun Life', ticker: 'SLF.TO', investorRelationsUrl: 'https://example.com/slf' },
  ],
  periods: [
    { key: 'T1', type: 'quarter', year: 2025, quarter: 1, endDate: '2025-03-31', label: 'T1 2025' },
    { key: 'AN', type: 'annual', year: 2025, quarter: null, endDate: '2025-12-31', label: 'Annuel 2025' },
  ],
  observations: [{
    id: 'MFC-2025-T1-core_eps', companyId: 'MFC', period: { key: 'T1', type: 'quarter', year: 2025, quarter: 1, endDate: '2025-03-31', label: 'T1 2025' },
    metricId: 'core_eps', label: 'BPA de base', value: 1.25, unit: 'CAD_PER_SHARE', displayValue: '1,25 $',
    comparison: { value: 1, displayValue: '1,00 $', periodLabel: 'T1 2024', change: 0.25, changeUnit: 'PERCENT', displayChange: '+25 %' },
    direction: 'up', note: 'Note "citée"',
    source: { sourceId: 'mfc', url: 'https://example.com/source', title: 'Résultats', publishedAt: '2025-05-01', fetchedAt: '2026-07-10T12:00:00Z', documentHash: `sha256:${'a'.repeat(64)}`, priority: 'primary' },
    quality: { status: 'validated', extractionMethod: 'deterministic', confidence: 1, warnings: [] },
  }],
  news: [{
    id: 'news-1', companyIds: ['MFC'], periodKey: 'T1', publishedAt: '2025-05-01',
    source: { type: 'official_ir', name: 'Manuvie', url: 'https://example.com/news' }, title: 'Résultats du trimestre',
    originalSummary: 'Résumé.', generatedSummary: null, categories: ['financial_results'], importance: 'high', themes: ['résultats'],
    quality: { status: 'validated', extractionMethod: 'deterministic', confidence: 1, warnings: [] },
  }],
};

export const manifest: DatasetManifest = {
  schemaVersion: '1.0.0', generatedAt: '2026-07-10T12:00:00Z', datasetHash: `sha256:${'a'.repeat(64)}`,
  observationCount: 1, newsCount: 1, companyCount: 2, lastSuccessfulRefresh: '2026-07-10T12:00:00Z',
};

export const quality: QualityReport = {
  generatedAt: '2026-07-10T12:00:00Z', status: 'success', sourcesChecked: 2, sourcesSucceeded: 2,
  sourcesFailed: 0, observationsAdded: 0, observationsUpdated: 0, overridesApplied: 0, warnings: [], errors: [],
};
