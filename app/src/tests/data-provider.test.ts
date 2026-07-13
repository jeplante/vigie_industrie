import { describe, expect, it, vi } from "vitest";
import { StaticJsonDataProvider } from "../data/StaticJsonDataProvider";
import { dataset, manifest, quality } from "./fixtures";

describe("StaticJsonDataProvider", () => {
  it("charge et valide les trois documents", async () => {
    const values = [dataset, manifest, quality];
    const fetcher = vi.fn(
      async () => new Response(JSON.stringify(values.shift()), { status: 200 }),
    );
    const provider = new StaticJsonDataProvider("/data", fetcher);
    expect((await provider.loadDataset()).observations).toHaveLength(10);
    expect((await provider.loadManifest()).observationCount).toBe(10);
    expect((await provider.loadQualityReport()).status).toBe("success");
  });

  it("remonte une erreur de chargement explicite", async () => {
    const provider = new StaticJsonDataProvider(
      "/data",
      async () => new Response("", { status: 503 }),
    );
    await expect(provider.loadDataset()).rejects.toThrow("503");
  });
});
