import { type FormEvent, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { TextAreaField, FormField } from '@/components/FormField';
import { Icon } from '@/components/Icon';
import { ScheduleView } from '@/components/ScheduleView';
import {
  Alert,
  Avatar,
  Card,
  EmptyState,
  PageHeader,
  Pagination,
  QueryState,
  StatCard,
  Tabs,
} from '@/components/ui';
import { useAppointments } from '@/features/appointments/api';
import { AppointmentList } from '@/features/appointments/AppointmentList';
import { useAuth } from '@/features/auth/useAuth';
import { useChatUnread, useOpenConversation } from '@/features/chat/api';
import { ChatView } from '@/features/chat/ChatView';
import ProfilePage from '@/pages/ProfilePage';
import { getErrorMessage } from '@/lib/errors';
import { useClinicTimezone, useDebouncedValue } from '@/lib/hooks';
import { formatCalendarDate, formatDateTime, zonedToday } from '@/lib/time';

import {
  useDoctorProfile,
  useMyPatient,
  useMyPatients,
  useMySchedule,
  useUpdateDoctorProfile,
} from './api';

export function DoctorDashboard() {
  const { user } = useAuth();
  const timeZone = useClinicTimezone();
  const today = zonedToday(timeZone);
  const todays = useAppointments({ date_from: today, date_to: today, page_size: 50 });
  const upcoming = useAppointments({ scope: 'upcoming', page_size: 1 });
  const unread = useChatUnread();
  const active = todays.data?.items.filter(
    (a) => a.status === 'BOOKED' || a.status === 'CONFIRMED',
  );

  return (
    <div className="stack">
      <PageHeader
        title={`Good day, Dr. ${user?.last_name ?? user?.first_name ?? ''}`}
        description={formatCalendarDate(today, { weekday: 'long', day: 'numeric', month: 'long' })}
      />
      <div className="stat-grid">
        <StatCard icon="calendar" label="Today's appointments" value={active?.length ?? '–'} />
        <StatCard icon="list" label="Upcoming" value={upcoming.data?.total ?? '–'} />
        <StatCard icon="chat" label="Unread messages" value={unread.data?.unread ?? '–'} />
      </div>
      <Card title="Today" actions={<Link to="/doctor/appointments">All appointments</Link>}>
        <QueryState
          isLoading={todays.isLoading}
          error={todays.error}
          isEmpty={!todays.data?.items.length}
          empty={<EmptyState icon="calendar" title="No appointments today" />}
        >
          <AppointmentList appointments={todays.data?.items ?? []} perspective="doctor" />
        </QueryState>
      </Card>
    </div>
  );
}

export function DoctorAppointmentsPage() {
  const timeZone = useClinicTimezone();
  const [scope, setScope] = useState<'today' | 'upcoming' | 'past'>('today');
  const [page, setPage] = useState(1);
  const today = zonedToday(timeZone);
  const query =
    scope === 'today' ? { date_from: today, date_to: today, page, page_size: 50 } : { scope, page };
  const appointments = useAppointments(query);

  return (
    <div className="stack">
      <PageHeader title="Appointments" />
      <Tabs
        tabs={[
          { value: 'today', label: 'Today' },
          { value: 'upcoming', label: 'Upcoming' },
          { value: 'past', label: 'Past' },
        ]}
        value={scope}
        onChange={(value) => {
          setScope(value);
          setPage(1);
        }}
      />
      <Card>
        <QueryState
          isLoading={appointments.isLoading}
          error={appointments.error}
          isEmpty={!appointments.data?.items.length}
          empty={<EmptyState icon="calendar" title="Nothing here" />}
        >
          <AppointmentList appointments={appointments.data?.items ?? []} perspective="doctor" />
          <Pagination page={page} pages={appointments.data?.pages ?? 1} onChange={setPage} />
        </QueryState>
      </Card>
    </div>
  );
}

export function DoctorPatientsPage() {
  const timeZone = useClinicTimezone();
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const debounced = useDebouncedValue(search.trim());
  const patients = useMyPatients({ page, search: debounced || undefined });

  return (
    <div className="stack">
      <PageHeader title="Patients" description="Patients who have booked with you." />
      <label className="search-input">
        <Icon name="search" size={18} />
        <input
          type="search"
          placeholder="Search by name"
          aria-label="Search patients"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
        />
      </label>
      <Card>
        <QueryState
          isLoading={patients.isLoading}
          error={patients.error}
          isEmpty={!patients.data?.items.length}
          empty={<EmptyState icon="users" title="No patients yet" />}
        >
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Patient</th>
                  <th scope="col">Visits</th>
                  <th scope="col">Latest appointment</th>
                </tr>
              </thead>
              <tbody>
                {patients.data?.items.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <Link to={`/doctor/patients/${p.id}`} className="row">
                        <Avatar name={p.full_name} url={p.avatar_url} size={32} />
                        {p.full_name}
                      </Link>
                    </td>
                    <td>{p.appointment_count}</td>
                    <td>
                      {p.last_appointment_at
                        ? formatDateTime(p.last_appointment_at, timeZone)
                        : '–'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pages={patients.data?.pages ?? 1} onChange={setPage} />
        </QueryState>
      </Card>
    </div>
  );
}

export function DoctorPatientDetailPage() {
  const id = Number(useParams().patientId);
  const patient = useMyPatient(id);
  const appointments = useAppointments({ patient_id: id, page_size: 20 });
  const openChat = useOpenConversation();
  const navigate = useNavigate();

  return (
    <div className="stack">
      <Link to="/doctor/patients" className="small-text">
        ← All patients
      </Link>
      <QueryState isLoading={patient.isLoading} error={patient.error}>
        {patient.data && (
          <>
            <PageHeader
              title={patient.data.full_name}
              actions={
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    openChat.mutate(
                      { patient_id: id },
                      { onSuccess: (c) => void navigate(`/doctor/messages/${c.id}`) },
                    )
                  }
                >
                  <Icon name="chat" size={18} /> Message
                </button>
              }
            />
            {openChat.isError && <Alert>{getErrorMessage(openChat.error)}</Alert>}
            <Card title="Details">
              <dl className="details">
                <dt>Email</dt>
                <dd>{patient.data.email}</dd>
                <dt>Phone</dt>
                <dd>{patient.data.phone ?? '–'}</dd>
                <dt>Date of birth</dt>
                <dd>{patient.data.date_of_birth ?? '–'}</dd>
                <dt>Gender</dt>
                <dd>{patient.data.gender ?? '–'}</dd>
              </dl>
            </Card>
            <Card title="Appointments with you">
              <QueryState isLoading={appointments.isLoading} error={appointments.error}>
                <AppointmentList
                  appointments={appointments.data?.items ?? []}
                  perspective="doctor"
                />
              </QueryState>
            </Card>
          </>
        )}
      </QueryState>
    </div>
  );
}

export function DoctorMessagesPage() {
  const id = Number(useParams().conversationId) || null;
  return (
    <div className="stack fill">
      <PageHeader title="Messages" />
      <ChatView basePath="/doctor/messages" conversationId={id} />
    </div>
  );
}

export function DoctorSchedulePage() {
  const schedule = useMySchedule();
  return (
    <div className="stack">
      <PageHeader
        title="My schedule"
        description="Managed by the clinic administrator. Contact them to request changes."
      />
      <Card>
        <QueryState isLoading={schedule.isLoading} error={schedule.error}>
          {schedule.data && (
            <ScheduleView
              rules={schedule.data.rules}
              timeOff={schedule.data.time_off}
              timeZone={schedule.data.timezone}
            />
          )}
        </QueryState>
      </Card>
    </div>
  );
}

function ProfessionalProfile() {
  const profile = useDoctorProfile();
  const update = useUpdateDoctorProfile();
  const [draft, setDraft] = useState<{ bio: string; qualification: string } | null>(null);
  const values = draft ?? {
    bio: profile.data?.bio ?? '',
    qualification: profile.data?.qualification ?? '',
  };

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate(
      { bio: values.bio.trim() || null, qualification: values.qualification.trim() || null },
      { onSuccess: () => setDraft(null) },
    );
  }

  return (
    <Card title="Professional profile">
      <QueryState isLoading={profile.isLoading} error={profile.error}>
        <form className="stack" onSubmit={submit}>
          <div className="chips">
            {profile.data?.specializations.map((s) => (
              <span key={s.id} className="chip">
                {s.name}
              </span>
            ))}
            <span className="muted small-text">
              {profile.data?.experience_years} years experience · specializations are managed by the
              administrator
            </span>
          </div>
          {update.isSuccess && !draft && <Alert tone="success">Saved.</Alert>}
          {update.isError && <Alert>{getErrorMessage(update.error)}</Alert>}
          <FormField
            label="Qualification"
            value={values.qualification}
            maxLength={255}
            onChange={(e) => setDraft({ ...values, qualification: e.target.value })}
          />
          <TextAreaField
            label="Bio"
            rows={5}
            maxLength={2000}
            value={values.bio}
            onChange={(e) => setDraft({ ...values, bio: e.target.value })}
          />
          <div className="row">
            <button type="submit" disabled={update.isPending || !draft}>
              Save
            </button>
          </div>
        </form>
      </QueryState>
    </Card>
  );
}

export function DoctorProfilePage() {
  return (
    <div className="stack">
      <ProfilePage />
      <ProfessionalProfile />
    </div>
  );
}
