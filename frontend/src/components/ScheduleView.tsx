import { formatDateTime, WEEKDAYS } from '@/lib/time';
import type { ScheduleRule, TimeOff } from '@/lib/types';

const trim = (time: string) => time.slice(0, 5);

/** Read-only weekly schedule + time off. */
export function ScheduleView({
  rules,
  timeOff = [],
  timeZone,
}: {
  rules: ScheduleRule[];
  timeOff?: TimeOff[];
  timeZone: string;
}) {
  return (
    <div className="stack">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Day</th>
            <th scope="col">Working hours ({timeZone})</th>
          </tr>
        </thead>
        <tbody>
          {WEEKDAYS.map((day, index) => {
            const periods = rules.filter((r) => r.weekday === index);
            return (
              <tr key={day}>
                <th scope="row">{day}</th>
                <td>
                  {periods.length ? (
                    periods.map((p) => (
                      <span key={`${p.start_time}-${p.end_time}`} className="chip">
                        {trim(p.start_time)}–{trim(p.end_time)}
                        {p.effective_from || p.effective_until
                          ? ` (${p.effective_from ?? '…'} → ${p.effective_until ?? '…'})`
                          : ''}
                      </span>
                    ))
                  ) : (
                    <span className="muted">Off</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {timeOff.length > 0 && (
        <div>
          <h3>Time off</h3>
          <ul className="plain-list">
            {timeOff.map((t) => (
              <li key={t.id}>
                <span className="badge badge-neutral">
                  {t.doctor_id ? t.kind.toLowerCase() : 'clinic holiday'}
                </span>{' '}
                {formatDateTime(t.starts_at, timeZone)} → {formatDateTime(t.ends_at, timeZone)}
                {t.reason ? ` · ${t.reason}` : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
