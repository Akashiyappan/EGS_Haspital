/**
 * Timezone helpers. The API exchanges UTC instants; schedules and slot dates
 * are expressed in the clinic timezone (from GET /meta). Everything shown to
 * users is rendered in the clinic timezone so patients and staff agree on times.
 */

const partsCache = new Map<string, Intl.DateTimeFormat>();

function partsFormatter(timeZone: string): Intl.DateTimeFormat {
  let formatter = partsCache.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    partsCache.set(timeZone, formatter);
  }
  return formatter;
}

function zonedParts(date: Date, timeZone: string) {
  const parts = partsFormatter(timeZone).formatToParts(date);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  return {
    year: get('year'),
    month: get('month'),
    day: get('day'),
    hour: get('hour'),
    minute: get('minute'),
    second: get('second'),
  };
}

/** Offset (ms) of `timeZone` from UTC at the given instant. */
export function timeZoneOffsetMs(date: Date, timeZone: string): number {
  const p = zonedParts(date, timeZone);
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second);
  return asUtc - Math.floor(date.getTime() / 1000) * 1000;
}

/** Convert a wall-clock time in `timeZone` ("YYYY-MM-DDTHH:mm") to a UTC Date. */
export function zonedLocalToUtc(local: string, timeZone: string): Date {
  const [datePart, timePart = '00:00'] = local.split('T');
  const [y, m, d] = (datePart ?? '').split('-').map(Number);
  const [hh, mm] = timePart.split(':').map(Number);
  const wallClock = Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1, hh ?? 0, mm ?? 0);
  // Two passes settle the offset around DST boundaries.
  let utc = wallClock - timeZoneOffsetMs(new Date(wallClock), timeZone);
  utc = wallClock - timeZoneOffsetMs(new Date(utc), timeZone);
  return new Date(utc);
}

/** UTC instant -> "YYYY-MM-DDTHH:mm" wall-clock in `timeZone` (for datetime-local inputs). */
export function utcToZonedLocal(date: Date | string, timeZone: string): string {
  const p = zonedParts(new Date(date), timeZone);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`;
}

/** Today's date ("YYYY-MM-DD") in `timeZone`. */
export function zonedToday(timeZone: string, now: Date = new Date()): string {
  return utcToZonedLocal(now, timeZone).slice(0, 10);
}

/** Add days to a "YYYY-MM-DD" calendar date. */
export function addDays(isoDate: string, days: number): string {
  const [y, m, d] = isoDate.split('-').map(Number);
  const date = new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, (d ?? 1) + days));
  return date.toISOString().slice(0, 10);
}

export function formatDate(value: string | Date, timeZone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(value));
}

export function formatTime(value: string | Date, timeZone: string): string {
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(value));
}

export function formatDateTime(value: string | Date, timeZone: string): string {
  return `${formatDate(value, timeZone)}, ${formatTime(value, timeZone)}`;
}

/** Format a calendar date string ("YYYY-MM-DD") without shifting it across zones. */
export function formatCalendarDate(
  isoDate: string,
  options: Intl.DateTimeFormatOptions = { weekday: 'short', day: 'numeric', month: 'short' },
): string {
  return new Intl.DateTimeFormat(undefined, { ...options, timeZone: 'UTC' }).format(
    new Date(`${isoDate}T00:00:00Z`),
  );
}

export function formatRelative(value: string | Date, now: Date = new Date()): string {
  const diff = (new Date(value).getTime() - now.getTime()) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['day', 86400],
    ['hour', 3600],
    ['minute', 60],
  ];
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
  for (const [unit, seconds] of units) {
    if (Math.abs(diff) >= seconds) return rtf.format(Math.round(diff / seconds), unit);
  }
  return rtf.format(Math.round(diff), 'second');
}

export const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];
