import type { DatasetManifest, QualityReport, VigieDataset } from '../domain/models';

export interface DataProvider {
  loadDataset(): Promise<VigieDataset>;
  loadManifest(): Promise<DatasetManifest>;
  loadQualityReport(): Promise<QualityReport>;
}
