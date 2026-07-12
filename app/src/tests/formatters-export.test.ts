import { describe, expect, it } from 'vitest';
import { formatNumericValue } from '../formatters/currency';
import { formatChange } from '../formatters/percentage';
import { createCsv } from '../export/export-csv';
import { dataset } from './fixtures';

describe('formatage et export', () => {
  it('formate les devises et variations en français', () => {
    expect(formatNumericValue(1.25, 'CAD_PER_SHARE')).toContain('1,25');
    expect(formatChange(0.125, 'PERCENT')).toBe('+13 %');
  });

  it('produit un CSV Excel avec BOM, sources, qualité et guillemets échappés', () => {
    const csv = createCsv(dataset);
    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv).toContain('https://example.com/source');
    expect(csv).toContain('validated');
    expect(csv).toContain('"Note ""citée"""');
  });
});
