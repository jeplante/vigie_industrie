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

  it("appelle le fetch global avec le contexte Window", async () => {
    const contextualFetch = vi.fn(function (this: typeof globalThis) {
      if (this !== globalThis) throw new TypeError("Illegal invocation");
      return Promise.resolve(
        new Response(JSON.stringify(dataset), { status: 200 }),
      );
    });
    vi.stubGlobal("fetch", contextualFetch);

    try {
      const provider = new StaticJsonDataProvider("/data");
      await expect(provider.loadDataset()).resolves.toEqual(dataset);
      expect(contextualFetch).toHaveBeenCalledWith("/data/vigie.json", {
        cache: "no-cache",
      });
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
