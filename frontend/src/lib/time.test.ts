import { describe, expect, it } from 'vitest';

import { addDays, utcToZonedLocal, zonedLocalToUtc, zonedToday } from './time';

describe('timezone helpers', () => {
  it('converts clinic wall-clock time to UTC (Asia/Kolkata, +05:30)', () => {
    expect(zonedLocalToUtc('2030-01-07T08:00', 'Asia/Kolkata').toISOString()).toBe(
      '2030-01-07T02:30:00.000Z',
    );
  });

  it('round-trips UTC to wall-clock', () => {
    expect(utcToZonedLocal('2030-01-07T02:30:00Z', 'Asia/Kolkata')).toBe('2030-01-07T08:00');
  });

  it('handles DST in zones that observe it', () => {
    // New York: EST (-5) in January, EDT (-4) in July.
    expect(zonedLocalToUtc('2030-01-15T09:00', 'America/New_York').toISOString()).toBe(
      '2030-01-15T14:00:00.000Z',
    );
    expect(zonedLocalToUtc('2030-07-15T09:00', 'America/New_York').toISOString()).toBe(
      '2030-07-15T13:00:00.000Z',
    );
  });

  it('computes the clinic date, not the browser date', () => {
    // 20:00 UTC is already the next day in Kolkata.
    expect(zonedToday('Asia/Kolkata', new Date('2030-01-07T20:00:00Z'))).toBe('2030-01-08');
    expect(zonedToday('UTC', new Date('2030-01-07T20:00:00Z'))).toBe('2030-01-07');
  });

  it('adds days across month boundaries', () => {
    expect(addDays('2030-01-31', 1)).toBe('2030-02-01');
    expect(addDays('2030-03-01', -1)).toBe('2030-02-28');
  });
});
