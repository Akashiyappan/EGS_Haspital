import { WEEKDAYS } from '@/lib/time';
import type { ScheduleRule } from '@/lib/types';

export interface Period {
  key: string;
  weekday: number;
  start_time: string;
  end_time: string;
  effective_from: string;
  effective_until: string;
}

let nextKey = 0;
export const toPeriod = (rule: ScheduleRule): Period => ({
  key: `p${nextKey++}`,
  weekday: rule.weekday,
  start_time: rule.start_time.slice(0, 5),
  end_time: rule.end_time.slice(0, 5),
  effective_from: rule.effective_from ?? '',
  effective_until: rule.effective_until ?? '',
});

export function validatePeriods(periods: Period[], slotMinutes: number): string | null {
  const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
  for (const p of periods) {
    if (!p.start_time || !p.end_time) return `${WEEKDAYS[p.weekday]}: enter start and end times`;
    if (minutes(p.end_time) - minutes(p.start_time) < slotMinutes) {
      return `${WEEKDAYS[p.weekday]}: a period must be at least ${slotMinutes} minutes`;
    }
  }
  for (const a of periods) {
    for (const b of periods) {
      if (a === b || a.weekday !== b.weekday) continue;
      const datesOverlap =
        (a.effective_from || '0000') <= (b.effective_until || '9999') &&
        (b.effective_from || '0000') <= (a.effective_until || '9999');
      if (datesOverlap && a.start_time < b.end_time && b.start_time < a.end_time) {
        return `${WEEKDAYS[a.weekday]}: working periods overlap`;
      }
    }
  }
  return null;
}
