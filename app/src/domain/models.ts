export type CompanyId = "MFC" | "SLF" | "GWO" | "IAG" | string;
export type PeriodKey = "T1" | "T2" | "T3" | "AN";
export type Direction = "up" | "down" | "neutral";
export type QualityStatus = "validated" | "warning" | "rejected";
export type ReportStatus = "success" | "partial" | "failed";
export type Importance = "high" | "medium" | "low";
export type RunMode = "offline" | "live" | "migration";

export interface Company {
  id: CompanyId;
  name: string;
  fullName: string;
  ticker: string;
  investorRelationsUrl: string;
}

export interface Period {
  periodId: string;
  periodKey: PeriodKey;
  type: "quarter" | "annual";
  year: number;
  quarter: number | null;
  endDate: string;
  label: string;
}

export interface SourceReference {
  sourceId: string;
  url: string;
  title: string;
  publishedAt: string;
  fetchedAt: string;
  documentHash: string;
  priority: "primary" | "secondary";
}

export interface ObservationQuality {
  status: QualityStatus;
  extractionMethod: string;
  confidence: number;
  warnings: string[];
  llmTrace?: {
    provider: string;
    model: string;
    promptVersion: string;
    executedAt: string;
    taskId: string;
    sourceFingerprint: string;
    confidence: number;
    warnings: string[];
  } | null;
}

export interface Comparison {
  periodId: string | null;
  value: number | null;
  displayValue: string;
  periodLabel: string;
  change: number | null;
  changeUnit: "PERCENT" | "PERCENTAGE_POINT" | "NONE";
  displayChange: string;
}

export interface Observation {
  id: string;
  companyId: CompanyId;
  period: Period;
  metricId: string;
  label: string;
  value: number;
  unit: string;
  displayValue: string;
  comparison: Comparison;
  direction: Direction;
  note: string;
  source: SourceReference;
  quality: ObservationQuality;
}

export interface NewsItem {
  id: string;
  companyIds: CompanyId[];
  periodId: string;
  periodKey: PeriodKey;
  publishedAt: string;
  source: {
    type:
      "official_ir" | "official_release" | "specialized_media" | "secondary";
    name: string;
    url: string;
    sourceId?: string | null;
    fetchedAt?: string | null;
    documentHash?: string | null;
  };
  title: string;
  originalSummary: string | null;
  generatedSummary: string | null;
  categories: string[];
  importance: Importance;
  themes: string[];
  quality: ObservationQuality;
}

export interface VigieDataset {
  schemaVersion: string;
  generatedAt: string;
  companies: Company[];
  periods: Period[];
  observations: Observation[];
  news: NewsItem[];
}

export interface DatasetManifest {
  schemaVersion: string;
  generatedAt: string;
  mode: RunMode;
  datasetHash: string;
  observationCount: number;
  newsCount: number;
  companyCount: number;
  lastAttemptAt: string;
  lastSuccessfulRefresh: string;
  companyFreshness: CompanyFreshness[];
}

export interface CompanyFreshness {
  companyId: CompanyId;
  latestAvailablePeriodId: string | null;
  latestPublishedPeriodId: string | null;
  latestSourceCheckAt: string | null;
  freshnessStatus: "current" | "stale" | "unknown";
}

export interface QualityIssue {
  code: string;
  message: string;
  sourceId?: string;
}

export interface QualityReport {
  generatedAt: string;
  mode: RunMode;
  dryRun: boolean;
  status: ReportStatus;
  sourcesChecked: number;
  sourcesSucceeded: number;
  sourcesFailed: number;
  observationsAdded: number;
  observationsUpdated: number;
  overridesApplied: number;
  warnings: QualityIssue[];
  errors: QualityIssue[];
  sourceResults: SourceRunResult[];
}

export interface SourceRunResult {
  sourceId: string;
  companyId: CompanyId;
  status: "success" | "warning" | "failed";
  documentsDiscovered: number;
  documentUrls: string[];
  periodIds: string[];
  message: string | null;
  anthropicCalls: number;
}
