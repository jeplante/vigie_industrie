import type { DataProvider } from './DataProvider';
import type { DatasetManifest, QualityReport, VigieDataset } from '../domain/models';
import { validateDataset, validateManifest, validateQualityReport } from '../domain/validators';

export class StaticJsonDataProvider implements DataProvider {
  public constructor(
    private readonly baseUrl = `${import.meta.env.BASE_URL}data`,
    private readonly fetcher: typeof fetch = fetch,
  ) {}

  private async load(path: string): Promise<unknown> {
    const response = await this.fetcher(`${this.baseUrl}/${path}`, { cache: 'no-cache' });
    if (!response.ok) throw new Error(`Erreur HTTP ${response.status} pendant le chargement.`);
    return response.json() as Promise<unknown>;
  }

  public async loadDataset(): Promise<VigieDataset> {
    return validateDataset(await this.load('vigie.json'));
  }

  public async loadManifest(): Promise<DatasetManifest> {
    return validateManifest(await this.load('manifest.json'));
  }

  public async loadQualityReport(): Promise<QualityReport> {
    return validateQualityReport(await this.load('quality-report.json'));
  }
}
