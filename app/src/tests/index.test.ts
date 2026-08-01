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
});
