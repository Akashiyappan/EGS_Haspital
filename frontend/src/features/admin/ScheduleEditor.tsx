import { useState } from 'react';

import { Icon } from '@/components/Icon';
import { Alert, LoadingBlock } from '@/components/ui';
import { getErrorMessage } from '@/lib/errors';
import { useMeta } from '@/lib/hooks';
import { WEEKDAYS } from '@/lib/time';

import { useDoctorSchedule, useSaveSchedule } from './api';
import { type Period, toPeriod, validatePeriods } from './schedule';

/** Weekly schedule editor: several working periods per weekday, optional date range. */
export function ScheduleEditor({ doctorId }: { doctorId: number }) {
  const meta = useMeta();
  const schedule = useDoctorSchedule(doctorId);
  if (schedule.isLoading) return <LoadingBlock />;
  if (schedule.error) return <Alert>{getErrorMessage(schedule.error)}</Alert>;
  return (
    <ScheduleEditorForm
      key={schedule.dataUpdatedAt}
      doctorId={doctorId}
      initial={(schedule.data?.rules ?? []).map(toPeriod)}
      timeZone={schedule.data?.timezone ?? meta.clinic_timezone}
      slotMinutes={meta.appointment_duration_minutes}
    />
  );
}

function ScheduleEditorForm({
  doctorId,
  initial,
  timeZone,
  slotMinutes,
}: {
  doctorId: number;
  initial: Period[];
  timeZone: string;
  slotMinutes: number;
}) {
  const save = useSaveSchedule(doctorId);
  const [periods, setPeriods] = useState<Period[]>(initial);
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<number[] | null>(null);

  function update(key: string, patch: Partial<Period>) {
    setPeriods((current) => current.map((p) => (p.key === key ? { ...p, ...patch } : p)));
  }

  function add(weekday: number) {
    setPeriods((current) => [
      ...current,
      toPeriod({ weekday, start_time: '08:00', end_time: '10:00' }),
    ]);
  }

  function submit() {
    const invalid = validatePeriods(periods, slotMinutes);
    setError(invalid);
    if (invalid) return;
    save.mutate(
      periods.map((p) => ({
        weekday: p.weekday,
        start_time: p.start_time,
        end_time: p.end_time,
        effective_from: p.effective_from || null,
        effective_until: p.effective_until || null,
      })),
      { onSuccess: (result) => setConflicts(result.conflicting_appointment_ids) },
    );
  }

  return (
    <div className="stack">
      <p className="muted small-text">
        Times are clinic time ({timeZone}). Appointments are offered every {slotMinutes} minutes
        inside each working period.
      </p>
      {error && <Alert>{error}</Alert>}
      {save.isError && <Alert>{getErrorMessage(save.error)}</Alert>}
      {conflicts && (
        <Alert tone={conflicts.length ? 'warning' : 'success'}>
          Schedule saved.
          {conflicts.length > 0 &&
            ` ${conflicts.length} upcoming appointment(s) no longer fit the schedule (IDs ${conflicts.join(', ')}). They were kept; review and cancel them if needed.`}
        </Alert>
      )}
      <div className="schedule-editor">
        {WEEKDAYS.map((day, weekday) => {
          const dayPeriods = periods.filter((p) => p.weekday === weekday);
          return (
            <div key={day} className="schedule-day">
              <div className="row space-between">
                <strong>{day}</strong>
                <button type="button" className="ghost small" onClick={() => add(weekday)}>
                  <Icon name="plus" size={16} /> Add period
                </button>
              </div>
              {dayPeriods.length === 0 && <span className="muted small-text">Not working</span>}
              {dayPeriods.map((p) => (
                <div key={p.key} className="period-row">
                  <input
                    type="time"
                    aria-label={`${day} start`}
                    value={p.start_time}
                    step={300}
                    onChange={(e) => update(p.key, { start_time: e.target.value })}
                  />
                  <span>to</span>
                  <input
                    type="time"
                    aria-label={`${day} end`}
                    value={p.end_time}
                    step={300}
                    onChange={(e) => update(p.key, { end_time: e.target.value })}
                  />
                  <details>
                    <summary className="small-text">Dates</summary>
                    <div className="row wrap">
                      <label className="small-text">
                        From{' '}
                        <input
                          type="date"
                          value={p.effective_from}
                          onChange={(e) => update(p.key, { effective_from: e.target.value })}
                        />
                      </label>
                      <label className="small-text">
                        Until{' '}
                        <input
                          type="date"
                          value={p.effective_until}
                          onChange={(e) => update(p.key, { effective_until: e.target.value })}
                        />
                      </label>
                    </div>
                  </details>
                  <button
                    type="button"
                    className="ghost icon-button"
                    aria-label={`Remove ${day} period`}
                    onClick={() => setPeriods((current) => current.filter((x) => x.key !== p.key))}
                  >
                    <Icon name="trash" size={16} />
                  </button>
                </div>
              ))}
            </div>
          );
        })}
      </div>
      <div className="row">
        <button type="button" onClick={submit} disabled={save.isPending}>
          {save.isPending ? 'Saving…' : 'Save schedule'}
        </button>
      </div>
    </div>
  );
}
