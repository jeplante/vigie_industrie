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
  container.setAttribute("aria-busy", "false");
  const age = ageInDays(manifest.lastSuccessfulRefresh, now);
  const stale = age > 7;
  const financialResults = report.sourceResults.filter((item) =>
    item.sourceId.endsWith("-results"),
  );
  const newsResults = report.sourceResults.filter(
    (item) => !item.sourceId.endsWith("-results"),
  );
  const financialFailures = financialResults.filter(
    (item) => item.status === "failed",
  ).length;
  const financialWarnings = financialResults.filter(
    (item) => item.status === "warning",
  ).length;
  const newsIssues = newsResults.filter(
    (item) => item.status !== "success",
  ).length;
  const staleCompanies = manifest.companyFreshness.filter(
    (item) => item.freshnessStatus === "stale",
  );
  const unknownCompanies = manifest.companyFreshness.filter(
    (item) => item.freshnessStatus === "unknown",
  );
  const financialConcern =
    financialFailures > 0 ||
    financialWarnings > 0 ||
    staleCompanies.length > 0 ||
    unknownCompanies.length > 0;
  const effectiveStatus =
    report.status === "failed"
      ? "failed"
      : financialConcern
        ? "partial"
        : "success";
  container.className = `status-panel status-${effectiveStatus}`;
  const statusLabel =
    report.status === "failed"
      ? "Publication bloquée"
      : financialConcern
        ? "Données financières publiées avec réserves"
        : "Données financières validées";
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
  if (financialFailures > 0) {
    container.append(
      element("span", {
        className: "source-warning",
        text: `${financialFailures} source${financialFailures > 1 ? "s" : ""} financière${financialFailures > 1 ? "s" : ""} bloquée${financialFailures > 1 ? "s" : ""}`,
      }),
    );
  }
  if (financialWarnings > 0) {
    container.append(
      element("span", {
        className: "source-warning",
        text: `${financialWarnings} source${financialWarnings > 1 ? "s" : ""} financière${financialWarnings > 1 ? "s" : ""} avec avertissement`,
      }),
    );
  }
  if (newsIssues > 0) {
    container.append(
      element("span", {
        className: "source-warning",
        text: `Actualités : ${newsIssues} source${newsIssues > 1 ? "s" : ""} avec avertissement`,
      }),
    );
  }
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
