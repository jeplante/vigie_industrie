import './styles.css';
import { StaticJsonDataProvider } from './data/StaticJsonDataProvider';
import type { DataProvider } from './data/DataProvider';
import type { AppState } from './ui/state';
import { initialState } from './ui/state';
import { requiredElement } from './ui/dom';
import { renderCompanyTabs } from './ui/render-company-tabs';
import { renderPeriodTabs } from './ui/render-period-tabs';
import { renderDashboard } from './ui/render-dashboard';
import { renderStatus } from './ui/render-status';
import { enableArrowNavigation } from './ui/accessibility';
import { downloadCsv } from './export/export-csv';

export class VigieApp {
  private state: AppState | null = null;

  public constructor(private readonly provider: DataProvider) {}

  public async start(): Promise<void> {
    const status = requiredElement('status');
    const errorPanel = requiredElement('load-error');
    status.hidden = false;
    status.setAttribute('aria-busy', 'true');
    errorPanel.hidden = true;
    try {
      const [dataset, manifest, report] = await Promise.all([
        this.provider.loadDataset(),
        this.provider.loadManifest(),
        this.provider.loadQualityReport(),
      ]);
      this.state = initialState(dataset);
      renderStatus(status, manifest, report);
      requiredElement('app-content').hidden = false;
      this.bindControls();
      this.render();
    } catch (error) {
      status.hidden = true;
      requiredElement('app-content').hidden = true;
      errorPanel.hidden = false;
      requiredElement('load-error-message').textContent =
        error instanceof Error ? error.message : 'Une erreur inconnue est survenue.';
    }
  }

  private bindControls(): void {
    const category = requiredElement<HTMLSelectElement>('news-category');
    category.replaceChildren(new Option('Toutes', 'all'));
    const categories = [...new Set(this.state?.dataset.news.flatMap((item) => item.categories) ?? [])].sort();
    for (const item of categories) category.append(new Option(item.replaceAll('_', ' '), item));
    category.onchange = () => {
      if (!this.state) return;
      this.state.category = category.value;
      this.render();
    };
    requiredElement<HTMLButtonElement>('export-csv').onclick = () => {
      if (this.state) downloadCsv(this.state.dataset);
    };
  }

  private render(): void {
    if (!this.state) return;
    const companyTabs = requiredElement('company-tabs');
    const periodTabs = requiredElement('period-tabs');
    renderCompanyTabs(companyTabs, this.state.dataset, this.state.companyId, (companyId) => {
      if (!this.state) return;
      this.state.companyId = companyId;
      this.render();
    });
    renderPeriodTabs(periodTabs, this.state.dataset.periods, this.state.periodKey, (periodKey) => {
      if (!this.state) return;
      this.state.periodKey = periodKey;
      this.render();
    });
    renderDashboard(this.state);
  }
}

const app = new VigieApp(new StaticJsonDataProvider());
enableArrowNavigation(requiredElement('company-tabs'));
enableArrowNavigation(requiredElement('period-tabs'));
requiredElement<HTMLButtonElement>('retry-load').addEventListener('click', () => void app.start());
void app.start();
