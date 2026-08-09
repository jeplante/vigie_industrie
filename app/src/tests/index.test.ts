import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("en-tête de la page", () => {
  it("propose un rafraîchissement sécurisé par GitHub Actions", () => {
    const indexPath = resolve(process.cwd(), "index.html");
    const html = readFileSync(indexPath, "utf8");

    expect(html).toContain('id="refresh-data"');
    expect(html).toContain(
      'href="https://github.com/jeplante/vigie_industrie/actions/workflows/refresh-data.yml"',
    );
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).not.toContain("github_pat_");
  });

  it("intègre l’historique à la synthèse avec le choix QTD ou YTD", () => {
    const indexPath = resolve(process.cwd(), "index.html");
    const html = readFileSync(indexPath, "utf8");

    const summaryStart = html.indexOf('id="summary-view"');
    const companyStart = html.indexOf('id="company-view"');
    const historyChart = html.indexOf('id="history-chart"');
    expect(historyChart).toBeGreaterThan(summaryStart);
    expect(historyChart).toBeLessThan(companyStart);
    expect(html).toContain('id="history-basis"');
    expect(html).toContain('<option value="qtd">QTD · Trimestre</option>');
    expect(html).toContain('<option value="ytd">YTD · Cumul annuel</option>');
    expect(html).not.toContain('data-view="history"');
    expect(html).not.toContain('id="history-view"');
  });
});
