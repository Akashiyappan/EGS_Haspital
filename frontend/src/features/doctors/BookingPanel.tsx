import { useState } from 'react';

import { TextAreaField } from '@/components/FormField';
import { Alert, EmptyState, QueryState } from '@/components/ui';
import { useBookAppointment } from '@/features/appointments/api';
import { getErrorMessage, getErrorStatus } from '@/lib/errors';
import { useMeta } from '@/lib/hooks';
import { formatCalendarDate, formatDateTime, formatTime, zonedToday } from '@/lib/time';
import type { Appointment, Slot } from '@/lib/types';

import { useAvailability, useSlots } from './api';

/**
 * Date strip + 30-minute slot picker. Availability comes entirely from the API;
 * a slot taken by someone else in the meantime surfaces as a 409 and the slots
 * are refreshed.
 */
export function BookingPanel({
  doctorId,
  onBooked,
}: {
  doctorId: number;
  onBooked: (appointment: Appointment) => void;
}) {
  const meta = useMeta();
  const timeZone = meta.clinic_timezone;
  const today = zonedToday(timeZone);
  const availability = useAvailability(doctorId, today);
  const [date, setDate] = useState<string | null>(null);
  const [slot, setSlot] = useState<Slot | null>(null);
  const [reason, setReason] = useState('');
  const book = useBookAppointment();

  const firstAvailable = availability.data?.days.find((d) => d.available_slots > 0)?.date ?? null;
  const activeDate = date ?? firstAvailable;
  const slotData = useSlots(doctorId, activeDate);

  function submit() {
    if (!slot) return;
    book.mutate(
      { doctor_id: doctorId, starts_at: slot.starts_at, reason: reason.trim() || undefined },
      {
        onSuccess: onBooked,
        onError: (error) => {
          if (getErrorStatus(error) === 409) {
            setSlot(null);
            void slotData.refetch();
          }
        },
      },
    );
  }

  return (
    <div className="stack">
      <QueryState
        isLoading={availability.isLoading}
        error={availability.error}
        onRetry={() => void availability.refetch()}
      >
        <div className="date-strip" role="listbox" aria-label="Choose a date">
          {availability.data?.days.map((day) => (
            <button
              key={day.date}
              type="button"
              role="option"
              aria-selected={day.date === activeDate}
              className={day.date === activeDate ? 'date-pill active' : 'date-pill'}
              disabled={day.available_slots === 0}
              onClick={() => {
                setDate(day.date);
                setSlot(null);
              }}
            >
              <span className="small-text">
                {formatCalendarDate(day.date, { weekday: 'short' })}
              </span>
              <strong>{formatCalendarDate(day.date, { day: 'numeric', month: 'short' })}</strong>
              <span className="small-text muted">
                {day.available_slots ? `${day.available_slots} free` : 'Full'}
              </span>
            </button>
          ))}
        </div>
      </QueryState>

      {!activeDate && availability.data && (
        <EmptyState
          icon="calendar"
          title="No availability in the next two weeks"
          description="Please check back later or choose another doctor."
        />
      )}

      {activeDate && (
        <QueryState isLoading={slotData.isLoading} error={slotData.error}>
          <fieldset className="slot-grid">
            <legend className="muted small-text">
              Times shown in clinic time ({timeZone}) · {meta.appointment_duration_minutes} min
            </legend>
            {slotData.data?.slots.map((s) => (
              <button
                key={s.starts_at}
                type="button"
                className={slot?.starts_at === s.starts_at ? 'slot active' : 'slot'}
                disabled={!s.available}
                aria-pressed={slot?.starts_at === s.starts_at}
                onClick={() => setSlot(s)}
              >
                {formatTime(s.starts_at, timeZone)}
              </button>
            ))}
            {slotData.data && slotData.data.slots.length === 0 && (
              <p className="muted">No slots on this day.</p>
            )}
          </fieldset>
        </QueryState>
      )}

      {slot && (
        <div className="stack booking-confirm">
          <p>
            Selected: <strong>{formatDateTime(slot.starts_at, timeZone)}</strong>
          </p>
          <TextAreaField
            label="Reason for visit (optional)"
            hint="Shared only with your doctor."
            value={reason}
            maxLength={1000}
            rows={3}
            onChange={(event) => setReason(event.target.value)}
          />
          {book.isError && <Alert>{getErrorMessage(book.error)}</Alert>}
          <button type="button" disabled={book.isPending} onClick={submit}>
            {book.isPending ? 'Booking…' : 'Confirm booking'}
          </button>
        </div>
      )}
    </div>
  );
}
