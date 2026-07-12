const DATE = new Intl.DateTimeFormat('fr-CA', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  timeZone: 'UTC',
});

const DATE_TIME = new Intl.DateTimeFormat('fr-CA', {
  dateStyle: 'long',
  timeStyle: 'short',
});

export const formatDate = (value: string): string => DATE.format(new Date(`${value}T12:00:00Z`));
export const formatDateTime = (value: string): string => DATE_TIME.format(new Date(value));

export function ageInDays(value: string, now = new Date()): number {
  return Math.floor((now.getTime() - new Date(value).getTime()) / 86_400_000);
}
