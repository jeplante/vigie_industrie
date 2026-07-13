import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import vm from 'node:vm';

const ROOT = resolve(import.meta.dirname, '..');
const LEGACY_PATH = resolve(ROOT, 'legacy/index-v1.html');
const PERIODS = {
  T1: { periodId: '2025-T1', periodKey: 'T1', type: 'quarter', year: 2025, quarter: 1, endDate: '2025-03-31', label: 'T1 2025' },
  T2: { periodId: '2025-T2', periodKey: 'T2', type: 'quarter', year: 2025, quarter: 2, endDate: '2025-06-30', label: 'T2 2025' },
  T3: { periodId: '2025-T3', periodKey: 'T3', type: 'quarter', year: 2025, quarter: 3, endDate: '2025-09-30', label: 'T3 2025' },
  AN: { periodId: '2025-AN', periodKey: 'AN', type: 'annual', year: 2025, quarter: null, endDate: '2025-12-31', label: 'Annuel 2025' },
};

const LABEL_TO_METRIC = new Map([
  ['BPA activités de base', 'core_eps'],
  ['BPA sous-jacent (dilué)', 'core_eps'],
  ['BPA de base (dilué)', 'core_eps'],
  ['BPA activités de base T4', 'core_eps_q4'],
  ['Résultat net actionnaires', 'net_income'],
  ['Revenu net sous-jacent', 'net_income'],
  ['Bénéfice de base', 'core_earnings'],
  ['Résultat activités de base', 'core_earnings'],
  ['Ratio LICAT (MLI)', 'licat_ratio'],
  ['Ratio LICAT (SLF Inc.)', 'licat_ratio'],
  ['Ratio LICAT', 'licat_ratio'],
  ['Ratio de solvabilité', 'solvency_ratio'],
  ['Actif sous gestion (AUM)', 'assets_under_management'],
  ['Actif sous gestion/admin.', 'assets_under_administration'],
  ['Actifs clients totaux', 'total_client_assets'],
]);

function sha(value) {
  return createHash('sha256').update(value).digest('hex');
}

function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([, item]) => item !== null)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, canonical(item)]),
    );
  }
  return value;
}

function parseLegacyData(html) {
  const start = html.indexOf('const DATA =') + 'const DATA ='.length;
  const scriptEnd = html.indexOf('let activeCompany', start);
  const end = html.lastIndexOf('};', scriptEnd);
  if (start < 12 || scriptEnd < 0 || end < 0) throw new Error('Objet DATA introuvable dans la V1.');
  return vm.runInNewContext(`(${html.slice(start, end + 1)})`, Object.create(null), { timeout: 1_000 });
}

function firstNumber(value) {
  const match = value.replaceAll('\u00a0', ' ').replaceAll('−', '-').match(/-?\d[\d ]*(?:[,.]\d+)?/u);
  if (!match) return null;
  return Number(match[0].replaceAll(' ', '').replace(',', '.'));
}

function unitFor(metric) {
  if (metric.value.includes('%')) return 'PERCENT';
  if (metric.value.includes('Bil $')) return 'CAD_TRILLION';
  if (metric.value.includes('G$')) return 'CAD_BILLION';
  if (metric.value.includes('M$')) return 'CAD_MILLION';
  if (metric.label.includes('BPA')) return 'CAD_PER_SHARE';
  return 'NUMBER';
}

function comparisonFor(metric, periodKey, year) {
  const isPoints = /\bpp\b/u.test(metric.delta);
  const isPercent = metric.delta.includes('%');
  const current = firstNumber(metric.value);
  const previous = firstNumber(metric.prev);
  const calculatedChange = current !== null && previous !== null
    ? isPercent && previous !== 0
      ? (current - previous) / Math.abs(previous)
      : isPoints
        ? current - previous
        : firstNumber(metric.delta)
    : null;
  const periodLabel = metric.prev.match(/\(([^)]+)\)/u)?.[1] ?? '';
  const comparisonYear = Number(periodLabel.match(/20\d{2}/u)?.[0]);
  const comparisonKey = periodLabel.match(/T[1-3]/u)?.[0] ?? (/^\s*20\d{2}\s*$/u.test(periodLabel) ? 'AN' : null);
  const validPeriod = comparisonYear === year - 1 && comparisonKey === periodKey;
  if (!validPeriod) {
    return {
      periodId: null,
      value: null,
      displayValue: '—',
      periodLabel: '',
      change: null,
      changeUnit: 'NONE',
      displayChange: '—',
    };
  }
  return {
    periodId: `${comparisonYear}-${comparisonKey}`,
    value: previous,
    displayValue: metric.prev,
    periodLabel,
    change: calculatedChange,
    changeUnit: isPoints ? 'PERCENTAGE_POINT' : isPercent ? 'PERCENT' : 'NONE',
    displayChange: metric.delta,
  };
}

function categoriesFor(news) {
  const text = `${news.title} ${news.desc}`.toLocaleLowerCase('fr');
  const categories = [];
  if (/résultat|earnings|trimestre|annuel|financial/u.test(text)) categories.push('financial_results');
  if (/dividende|rachat|capital|share repurchase/u.test(text)) categories.push('capital_management');
  if (/acquisition|fusion/u.test(text)) categories.push('merger_acquisition');
  if (/intelligence artificielle|\bia\b|\bai\b/u.test(text)) categories.push('artificial_intelligence');
  if (/numérique|digital/u.test(text)) categories.push('digital_transformation');
  return categories.length > 0 ? categories : ['other'];
}

function sourceType(url, companyCode) {
  const officialHosts = {
    MFC: ['manulife.com'], SLF: ['sunlife.com'], GWO: ['greatwestlifeco.com'], IAG: ['ia.ca'],
  };
  if (officialHosts[companyCode].some((host) => url.includes(host))) return 'official_ir';
  if (/newswire|businesswire|prnewswire/u.test(url)) return 'official_release';
  if (/finance-investissement|globeandmail|investing/u.test(url)) return 'specialized_media';
  return 'secondary';
}

function migrate(legacy) {
  const companies = [];
  const observations = [];
  const news = [];
  for (const [companyId, company] of Object.entries(legacy)) {
    companies.push({
      id: companyId,
      name: company.name,
      fullName: company.fullName,
      ticker: company.ticker,
      investorRelationsUrl: company.ir_url,
    });
    for (const [periodKey, period] of Object.entries(PERIODS)) {
      const legacyPeriod = company[periodKey];
      const sourceDate = legacyPeriod.news[0]?.date ?? period.endDate;
      legacyPeriod.metrics.forEach((metric, index) => {
        const value = firstNumber(metric.value);
        if (value === null) throw new Error(`Valeur non numérique: ${companyId}/${periodKey}/${metric.label}`);
        const metricId = LABEL_TO_METRIC.get(metric.label) ?? `legacy_metric_${index + 1}`;
        observations.push({
          id: `${companyId}-${period.periodId}-${metricId}`,
          companyId,
          period,
          metricId,
          label: metric.label,
          value,
          unit: unitFor(metric),
          displayValue: metric.value,
          comparison: comparisonFor(metric, periodKey, period.year),
          direction: metric.dir,
          note: metric.note,
          source: {
            sourceId: `${companyId.toLowerCase()}-results`,
            url: company.ir_url,
            title: `${company.name} — ${legacyPeriod.period}`,
            publishedAt: sourceDate,
            fetchedAt: '2026-07-11T00:00:00Z',
            documentHash: `sha256:${sha(`${company.ir_url}|${period.periodId}`)}`,
            priority: 'primary',
          },
          quality: {
            status: 'validated',
            extractionMethod: 'v1_migration',
            confidence: 1,
            warnings: ['Provenance migrée de la V1; empreinte calculée sur la référence de source.'],
          },
        });
      });
      legacyPeriod.news.forEach((item, index) => {
        const categories = categoriesFor(item);
        news.push({
          id: `news-${sha(`${companyId}|${periodKey}|${item.url}|${item.title}|${index}`).slice(0, 20)}`,
          companyIds: [companyId],
          periodId: period.periodId,
          periodKey,
          publishedAt: item.date,
          source: { type: sourceType(item.url, companyId), name: item.source, url: item.url },
          title: item.title,
          originalSummary: item.desc,
          generatedSummary: null,
          categories,
          importance: categories.includes('financial_results') ? 'high' : 'medium',
          themes: categories.map((category) => category.replaceAll('_', ' ')),
          quality: { status: 'validated', extractionMethod: 'v1_migration', confidence: 1, warnings: [] },
        });
      });
    }
  }
  return {
    schemaVersion: '2.0.0',
    generatedAt: '2026-07-11T00:00:00Z',
    companies,
    periods: Object.values(PERIODS),
    observations,
    news,
  };
}

async function writeJson(path, value) {
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
}

const html = await readFile(LEGACY_PATH, 'utf8');
const dataset = migrate(parseLegacyData(html));
if (dataset.companies.length !== 4 || dataset.observations.length !== 64 || dataset.news.length !== 48) {
  throw new Error(`Migration incomplète: ${dataset.companies.length}/64/${dataset.news.length}`);
}
const datasetHash = `sha256:${sha(JSON.stringify(canonical(dataset)))}`;
const manifest = {
  schemaVersion: '1.0.0',
  generatedAt: dataset.generatedAt,
  mode: 'migration',
  datasetHash,
  observationCount: dataset.observations.length,
  newsCount: dataset.news.length,
  companyCount: dataset.companies.length,
  lastAttemptAt: dataset.generatedAt,
  lastSuccessfulRefresh: dataset.generatedAt,
  companyFreshness: dataset.companies.map((company) => ({
    companyId: company.id,
    latestAvailablePeriodId: null,
    latestPublishedPeriodId: '2025-AN',
    latestSourceCheckAt: null,
    freshnessStatus: 'unknown',
  })),
};
const report = {
  generatedAt: dataset.generatedAt,
  mode: 'migration',
  dryRun: false,
  status: 'success',
  sourcesChecked: 0,
  sourcesSucceeded: 0,
  sourcesFailed: 0,
  observationsAdded: 64,
  observationsUpdated: 0,
  overridesApplied: 0,
  warnings: [],
  errors: [],
  sourceResults: [],
};

for (const base of ['data/seed', 'data/published', 'app/public/data']) {
  await writeJson(resolve(ROOT, base, base.endsWith('seed') ? 'vigie-v1.json' : 'vigie.json'), dataset);
  if (!base.endsWith('seed')) {
    await writeJson(resolve(ROOT, base, 'manifest.json'), manifest);
    await writeJson(resolve(ROOT, base, 'quality-report.json'), report);
  }
}

console.log(`Migration terminée: ${dataset.companies.length} compagnies, ${dataset.observations.length} observations, ${dataset.news.length} actualités.`);
