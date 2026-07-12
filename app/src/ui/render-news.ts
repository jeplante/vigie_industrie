import type { NewsItem } from '../domain/models';
import { formatDate } from '../formatters/date';
import { clear, element } from './dom';

export function renderNews(container: HTMLElement, items: NewsItem[]): void {
  clear(container);
  if (items.length === 0) {
    container.append(element('p', { className: 'empty-state', text: 'Aucune actualité pour ce filtre.' }));
    return;
  }
  for (const item of items) {
    const article = element('article', { className: 'news-item' });
    const meta = element('div', { className: 'news-meta' });
    meta.append(
      element('time', { text: formatDate(item.publishedAt) }),
      element('span', { className: `importance importance-${item.importance}`, text: item.importance }),
    );
    const title = element('a', { className: 'news-title', text: item.title });
    title.href = item.source.url;
    title.target = '_blank';
    title.rel = 'noopener noreferrer';
    article.append(meta, title);
    article.append(
      element('p', { className: 'news-source', text: item.source.name }),
      element('p', { text: item.generatedSummary ?? item.originalSummary ?? 'Aucun résumé disponible.' }),
    );
    const tags = element('ul', { className: 'tag-list' });
    for (const category of item.categories) tags.append(element('li', { text: category.replaceAll('_', ' ') }));
    article.append(tags);
    container.append(article);
  }
}
