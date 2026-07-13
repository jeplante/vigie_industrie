const NUMBER = new Intl.NumberFormat("fr-CA", { maximumFractionDigits: 3 });

export function formatNumericValue(value: number, unit: string): string {
  if (unit === "CAD_PER_SHARE") return `${NUMBER.format(value)} $`;
  if (unit === "CAD_BILLION") return `${NUMBER.format(value)} G$`;
  if (unit === "CAD_TRILLION") return `${NUMBER.format(value)} Bil $`;
  if (unit === "CAD_MILLION") return `${NUMBER.format(value)} M$`;
  if (unit === "PERCENT") return `${NUMBER.format(value)} %`;
  return NUMBER.format(value);
}
