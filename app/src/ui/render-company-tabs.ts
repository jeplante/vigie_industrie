import type { CompanyId, VigieDataset } from '../domain/models';
import { clear, element } from './dom';

export function renderCompanyTabs(
  container: HTMLElement,
  dataset: VigieDataset,
  activeId: CompanyId,
  onSelect: (id: CompanyId) => void,
): void {
  clear(container);
  for (const company of dataset.companies) {
    const button = element('button', { className: 'company-tab' });
    button.type = 'button';
    button.id = `company-tab-${company.id}`;
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-controls', 'company-panel');
    button.setAttribute('aria-selected', String(company.id === activeId));
    button.tabIndex = company.id === activeId ? 0 : -1;
    button.append(element('span', { text: company.name }));
    button.append(element('small', { text: company.ticker }));
    button.addEventListener('click', () => onSelect(company.id));
    container.append(button);
  }
}
