import type { Period } from "../domain/models";

export function shortPeriod(period: Period): string {
  return period.type === "annual"
    ? `Annuel ${period.year}`
    : `T${period.quarter} ${period.year}`;
}
