import type { DatasetManifest, QualityReport } from "../domain/models";
import { ageInDays, formatDateTime } from "../formatters/date";
import { clear, element } from "./dom";

export function renderStatus(
  container: HTMLElement,
  manifest: DatasetManifest,
  report: QualityReport,
  now = new Date(),
): void {
  clear(container);
  container.className = `status-panel status-${report.status}`;
  container.setAttribute("aria-busy", "false");
  const age = ageInDays(manifest.lastSuccessfulRefresh, now);
  const stale = age > 7;
  const statusLabel = {
    success: "Données validées",
    partial: "Données publiées avec réserves",
    failed: "Publication bloquée",
  }[report.status];
  container.append(
    element("strong", {
      text: statusLabel,
    }),
    element("span", {
      text: `Dernière tentative : ${formatDateTime(manifest.lastAttemptAt)}`,
    }),
    element("span", {
      text: `Dernier rafraîchissement financier réussi : ${formatDateTime(manifest.lastSuccessfulRefresh)}`,
    }),
    element("span", {
      text: `Mode : ${{ offline: "offline (hors ligne)", live: "live (en ligne)", migration: "migration" }[manifest.mode]}`,
    }),
  );
  if (stale)
    container.append(
      element("span", {
        className: "stale-warning",
        text: `Données anciennes (${age} jours)`,
      }),
    );
  const failedSources = report.sourceResults.filter(
    (item) => item.status === "failed",
  ).length;
  const warningSources = report.sourceResults.filter(
    (item) => item.status === "warning",
  ).length;
  if (failedSources > 0) {
    container.append(
      element("span", {
        className: "source-warning",
        text: `${failedSources} source${failedSources > 1 ? "s" : ""} bloquée${failedSources > 1 ? "s" : ""}`,
      }),
    );
  }
  if (warningSources > 0) {
    container.append(
      element("span", {
        className: "source-warning",
        text: `${warningSources} source${warningSources > 1 ? "s" : ""} avec avertissement`,
      }),
    );
  }
  const staleCompanies = manifest.companyFreshness.filter(
    (item) => item.freshnessStatus === "stale",
  );
  const unknownCompanies = manifest.companyFreshness.filter(
    (item) => item.freshnessStatus === "unknown",
  );
  if (staleCompanies.length > 0) {
    container.append(
      element("span", {
        className: "stale-warning",
        text: `${staleCompanies.length} compagnie${staleCompanies.length > 1 ? "s" : ""} avec un document plus récent non intégré`,
      }),
    );
  }
  if (unknownCompanies.length > 0) {
    container.append(
      element("span", {
        className: "source-warning",
        text: `Fraîcheur non vérifiée pour ${unknownCompanies.length} compagnie${unknownCompanies.length > 1 ? "s" : ""}`,
      }),
    );
  }
}
