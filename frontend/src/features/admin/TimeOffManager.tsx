import { type FormEvent, useState } from 'react';

import { FormField, SelectField } from '@/components/FormField';
import { Icon } from '@/components/Icon';
import { Alert, EmptyState, QueryState } from '@/components/ui';
import { getErrorMessage } from '@/lib/errors';
import { useClinicTimezone } from '@/lib/hooks';
import { formatDateTime, zonedLocalToUtc } from '@/lib/time';
import type { TimeOffKind } from '@/lib/types';

import { useAddTimeOff, useRemoveTimeOff, useTimeOff } from './api';

/** Leave / unavailability for one doctor, or clinic-wide holidays (`doctorId="clinic"`). */
export function TimeOffManager({ doctorId }: { doctorId: number | 'clinic' }) {
  const timeZone = useClinicTimezone();
  const entries = useTimeOff(doctorId);
  const add = useAddTimeOff(doctorId);
  const remove = useRemoveTimeOff();
  const clinic = doctorId === 'clinic';
  const [kind, setKind] = useState<TimeOffKind>(clinic ? 'HOLIDAY' : 'LEAVE');
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [conflicts, setConflicts] = useState<number[] | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!start || !end) return setError('Choose a start and end');
    const startsAt = zonedLocalToUtc(start, timeZone);
    const endsAt = zonedLocalToUtc(end, timeZone);
    if (endsAt <= startsAt) return setError('End must be after start');
    setError(null);
    add.mutate(
      {
        kind,
        starts_at: startsAt.toISOString(),
        ends_at: endsAt.toISOString(),
        reason: reason.trim() || undefined,
      },
      {
        onSuccess: (result) => {
          setConflicts(result.conflicting_appointment_ids);
          setStart('');
          setEnd('');
          setReason('');
        },
      },
    );
  }

  // For a doctor, show only their own entries here (clinic holidays are managed separately).
  const visible = entries.data?.filter((t) =>
    clinic ? t.doctor_id === null : t.doctor_id !== null,
  );

  return (
    <div className="stack">
      <form className="stack" onSubmit={submit}>
        <p className="muted small-text">
          Times are clinic time ({timeZone}). No slots are offered during time off; existing
          appointments are not cancelled automatically.
        </p>
        {error && <Alert>{error}</Alert>}
        {add.isError && <Alert>{getErrorMessage(add.error)}</Alert>}
        {conflicts && conflicts.length > 0 && (
          <Alert tone="warning">
            {conflicts.length} active appointment(s) overlap this period (IDs {conflicts.join(', ')}
            ). Review them under Appointments.
          </Alert>
        )}
        <div className="grid-4">
          {!clinic && (
            <SelectField
              label="Type"
              value={kind}
              onChange={(e) => setKind(e.target.value as TimeOffKind)}
            >
              <option value="LEAVE">Leave</option>
              <option value="UNAVAILABLE">Unavailable</option>
              <option value="HOLIDAY">Holiday</option>
            </SelectField>
          )}
          <FormField
            label="Starts"
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
          <FormField
            label="Ends"
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
          <FormField
            label="Reason (optional)"
            value={reason}
            maxLength={255}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="row">
          <button type="submit" disabled={add.isPending}>
            <Icon name="plus" size={16} /> {clinic ? 'Add holiday' : 'Add time off'}
          </button>
        </div>
      </form>
      <QueryState
        isLoading={entries.isLoading}
        error={entries.error}
        isEmpty={!visible?.length}
        empty={<EmptyState icon="clock" title="Nothing scheduled" />}
      >
        <ul className="plain-list">
          {visible?.map((t) => (
            <li key={t.id} className="row space-between">
              <span>
                <span className="badge badge-neutral">{t.kind.toLowerCase()}</span>{' '}
                {formatDateTime(t.starts_at, timeZone)} → {formatDateTime(t.ends_at, timeZone)}
                {t.reason ? ` · ${t.reason}` : ''}
              </span>
              <button
                type="button"
                className="ghost icon-button"
                aria-label="Remove"
                disabled={remove.isPending}
                onClick={() => remove.mutate(t.id)}
              >
                <Icon name="trash" size={16} />
              </button>
            </li>
          ))}
        </ul>
      </QueryState>
    </div>
  );
}
