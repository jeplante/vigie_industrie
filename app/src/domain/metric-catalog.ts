export interface MetricDefinition {
  id: string;
  label: string;
  unit: string;
  format: 'currency' | 'percentage' | 'number';
  comparison: 'percent' | 'percentage_point' | 'contextual';
  favorableTrend: 'up' | 'down' | 'contextual';
}

export const METRIC_CATALOG: MetricDefinition[] = [
  ['core_eps', 'BPA activités de base', 'CAD_PER_SHARE', 'currency', 'percent', 'up'],
  ['reported_eps', 'BPA déclaré', 'CAD_PER_SHARE', 'currency', 'percent', 'contextual'],
  ['core_earnings', 'Résultat activités de base', 'CAD_BILLION', 'currency', 'percent', 'up'],
  ['net_income', 'Résultat net', 'CAD_BILLION', 'currency', 'percent', 'up'],
  ['licat_ratio', 'Ratio LICAT', 'PERCENT', 'percentage', 'percentage_point', 'contextual'],
  ['solvency_ratio', 'Ratio de solvabilité', 'PERCENT', 'percentage', 'percentage_point', 'contextual'],
  ['assets_under_management', 'Actif sous gestion', 'CAD_BILLION', 'currency', 'percent', 'up'],
  ['assets_under_administration', 'Actif sous administration', 'CAD_BILLION', 'currency', 'percent', 'up'],
  ['total_client_assets', 'Actifs clients totaux', 'CAD_BILLION', 'currency', 'percent', 'up'],
  ['core_roe', 'Rendement des capitaux propres de base', 'PERCENT', 'percentage', 'percentage_point', 'up'],
  ['csm', 'Marge sur services contractuels', 'CAD_BILLION', 'currency', 'percent', 'up'],
  ['new_business_value', 'Valeur des affaires nouvelles', 'CAD_MILLION', 'currency', 'percent', 'up'],
  ['ape_sales', 'Souscriptions selon l’EPA', 'CAD_MILLION', 'currency', 'percent', 'up'],
  ['capital_available', 'Capital disponible', 'CAD_BILLION', 'currency', 'percent', 'contextual'],
].map(([id, label, unit, format, comparison, favorableTrend]) => ({
  id,
  label,
  unit,
  format,
  comparison,
  favorableTrend,
})) as MetricDefinition[];
