import { describe, expect, it, vi } from 'vitest';
import { enableArrowNavigation } from '../ui/accessibility';
import { renderCompanyTabs } from '../ui/render-company-tabs';
import { renderPeriodTabs } from '../ui/render-period-tabs';
import { renderNews } from '../ui/render-news';
import { renderStatus } from '../ui/render-status';
import { dataset, manifest, quality } from './fixtures';

describe('interface', () => {
  it('change de compagnie et de période', () => {
    const companies = document.createElement('div');
    const periods = document.createElement('div');
    const onCompany = vi.fn();
    const onPeriod = vi.fn();
    renderCompanyTabs(companies, dataset, 'MFC', onCompany);
    renderPeriodTabs(periods, dataset.periods, 'T1', onPeriod);
    companies.querySelectorAll('button')[1]?.click();
    periods.querySelectorAll('button')[1]?.click();
    expect(onCompany).toHaveBeenCalledWith('SLF');
    expect(onPeriod).toHaveBeenCalledWith('AN');
  });

  it('filtre les actualités avant rendu', () => {
    const container = document.createElement('div');
    renderNews(container, dataset.news.filter((item) => item.categories.includes('other')));
    expect(container.textContent).toContain('Aucune actualité');
  });

  it('affiche qualité, sources en erreur et données périmées', () => {
    const container = document.createElement('div');
    renderStatus(container, { ...manifest, lastSuccessfulRefresh: '2026-06-01T00:00:00Z' }, { ...quality, status: 'partial', sourcesFailed: 1 }, new Date('2026-07-11T00:00:00Z'));
    expect(container.textContent).toContain('Données anciennes');
    expect(container.textContent).toContain('1 source');
  });

  it('navigue entre les onglets au clavier', () => {
    const container = document.createElement('div');
    document.body.append(container);
    renderCompanyTabs(container, dataset, 'MFC', vi.fn());
    enableArrowNavigation(container);
    const buttons = container.querySelectorAll('button');
    buttons[0]?.focus();
    buttons[0]?.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(document.activeElement).toBe(buttons[1]);
  });
});
