import type { AppState } from './state';
import { renderMetrics } from './render-metrics';
import { renderNews } from './render-news';
import { clear, element, requiredElement } from './dom';

export function renderDashboard(state: AppState): void {
  const company = state.dataset.companies.find(({ id }) => id === state.companyId);
  if (!company) throw new Error(`Compagnie inconnue: ${state.companyId}`);
  const period = state.dataset.periods.find(({ key }) => key === state.periodKey);
  if (!period) throw new Error(`Période inconnue: ${state.periodKey}`);

  const header = requiredElement<HTMLDivElement>('company-header');
  clear(header);
  const titleWrap = element('div');
  titleWrap.append(
    element('p', { className: 'eyebrow', text: company.fullName }),
    element('h2', { text: `${company.name} · ${period.label}` }),
  );
  const irLink = element('a', { className: 'button', text: 'Relations investisseurs' });
  irLink.href = company.investorRelationsUrl;
  irLink.target = '_blank';
  irLink.rel = 'noopener noreferrer';
  header.append(titleWrap, irLink);

  renderMetrics(
    requiredElement('metrics'),
    state.dataset.observations.filter(
      ({ companyId, period: observationPeriod }) =>
        companyId === state.companyId && observationPeriod.key === state.periodKey,
    ),
  );
  renderNews(
    requiredElement('news'),
    state.dataset.news.filter(
      (item) =>
        item.companyIds.includes(state.companyId) &&
        item.periodKey === state.periodKey &&
        (state.category === 'all' || item.categories.includes(state.category)),
    ),
  );
  requiredElement('company-panel').setAttribute('aria-labelledby', `company-tab-${company.id}`);
}
