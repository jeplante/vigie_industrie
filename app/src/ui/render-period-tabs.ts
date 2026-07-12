import type { Period, PeriodKey } from '../domain/models';
import { shortPeriod } from '../formatters/period';
import { clear, element } from './dom';

export function renderPeriodTabs(
  container: HTMLElement,
  periods: Period[],
  activeKey: PeriodKey,
  onSelect: (key: PeriodKey) => void,
): void {
  clear(container);
  for (const period of periods) {
    const button = element('button', { className: 'period-tab', text: shortPeriod(period) });
    button.type = 'button';
    button.setAttribute('role', 'tab');
    button.setAttribute('aria-controls', 'company-panel');
    button.setAttribute('aria-selected', String(period.key === activeKey));
    button.tabIndex = period.key === activeKey ? 0 : -1;
    button.addEventListener('click', () => onSelect(period.key));
    container.append(button);
  }
}
