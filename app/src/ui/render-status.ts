import type { DatasetManifest, QualityReport } from '../domain/models';
import { ageInDays, formatDateTime } from '../formatters/date';
import { clear, element } from './dom';

export function renderStatus(
  container: HTMLElement,
  manifest: DatasetManifest,
  report: QualityReport,
  now = new Date(),
): void {
  clear(container);
  container.className = `status-panel status-${report.status}`;
  container.setAttribute('aria-busy', 'false');
  const age = ageInDays(manifest.lastSuccessfulRefresh, now);
  const stale = age > 7;
  container.append(
    element('strong', { text: report.status === 'success' ? 'Données validées' : 'Qualité dégradée' }),
    element('span', { text: `Dernier rafraîchissement : ${formatDateTime(manifest.lastSuccessfulRefresh)}` }),
  );
  if (stale) container.append(element('span', { className: 'stale-warning', text: `Données anciennes (${age} jours)` }));
  if (report.sourcesFailed > 0) {
    container.append(element('span', { className: 'source-warning', text: `${report.sourcesFailed} source(s) en erreur` }));
  }
}
