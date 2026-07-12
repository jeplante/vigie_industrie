export function formatChange(value: number | null, unit: string): string {
  if (value === null) return '—';
  const prefix = value > 0 ? '+' : '';
  if (unit === 'PERCENT') return `${prefix}${Math.round(value * 100)} %`;
  if (unit === 'PERCENTAGE_POINT') return `${prefix}${value} pp`;
  return value === 0 ? 'Stable' : `${prefix}${value}`;
}
