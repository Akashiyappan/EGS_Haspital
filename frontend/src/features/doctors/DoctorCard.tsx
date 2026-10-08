import type { ReactNode } from 'react';

import { Avatar } from '@/components/ui';
import type { DoctorPublic } from '@/lib/types';

export function DoctorCard({ doctor, actions }: { doctor: DoctorPublic; actions?: ReactNode }) {
  return (
    <article className="doctor-card">
      <div className="row">
        <Avatar name={doctor.full_name} url={doctor.avatar_url} size={56} />
        <div>
          <h3>Dr. {doctor.full_name}</h3>
          <div className="muted small-text">
            {doctor.qualification ?? 'Physician'} · {doctor.experience_years} yrs experience
          </div>
        </div>
      </div>
      <div className="chips">
        {doctor.specializations.map((s) => (
          <span key={s.id} className="chip">
            {s.name}
          </span>
        ))}
      </div>
      {doctor.bio && <p className="small-text clamp">{doctor.bio}</p>}
      {actions && <div className="row wrap">{actions}</div>}
    </article>
  );
}
