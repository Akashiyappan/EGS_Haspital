import { useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router';

import { Icon } from '@/components/Icon';
import { SelectField } from '@/components/FormField';
import {
  Alert,
  Card,
  EmptyState,
  PageHeader,
  Pagination,
  QueryState,
  StatCard,
  Tabs,
} from '@/components/ui';
import { AssistantView } from '@/features/ai/AssistantView';
import { useAppointments } from '@/features/appointments/api';
import { AppointmentList } from '@/features/appointments/AppointmentList';
import { useAuth } from '@/features/auth/useAuth';
import { useChatUnread, useOpenConversation } from '@/features/chat/api';
import { ChatView } from '@/features/chat/ChatView';
import { useDoctor, useDoctors, useSpecializations } from '@/features/doctors/api';
import { BookingPanel } from '@/features/doctors/BookingPanel';
import { DoctorCard } from '@/features/doctors/DoctorCard';
import { getErrorMessage } from '@/lib/errors';
import { useClinicTimezone, useDebouncedValue } from '@/lib/hooks';
import { formatDateTime } from '@/lib/time';

export function PatientDashboard() {
  const { user } = useAuth();
  const timeZone = useClinicTimezone();
  const upcoming = useAppointments({ scope: 'upcoming', page_size: 3 });
  const unread = useChatUnread();
  const next = upcoming.data?.items[0];

  return (
    <div className="stack">
      <PageHeader
        title={`Hello, ${user?.first_name ?? ''}`}
        description="Here's what's coming up."
        actions={
          <Link to="/patient/doctors" className="button">
            Book an appointment
          </Link>
        }
      />
      <div className="stat-grid">
        <StatCard
          icon="calendar"
          label="Next appointment"
          value={next ? formatDateTime(next.starts_at, timeZone) : 'None booked'}
        />
        <StatCard icon="list" label="Upcoming" value={upcoming.data?.total ?? '–'} />
        <StatCard icon="chat" label="Unread messages" value={unread.data?.unread ?? '–'} />
      </div>
      <div className="grid-2 align-start">
        <Card
          title="Upcoming appointments"
          actions={<Link to="/patient/appointments">View all</Link>}
        >
          <QueryState
            isLoading={upcoming.isLoading}
            error={upcoming.error}
            isEmpty={!upcoming.data?.items.length}
            empty={
              <EmptyState
                icon="calendar"
                title="No upcoming appointments"
                action={
                  <Link to="/patient/doctors" className="button small">
                    Find a doctor
                  </Link>
                }
              />
            }
          >
            <AppointmentList appointments={upcoming.data?.items ?? []} perspective="patient" />
          </QueryState>
        </Card>
        <Card title="Not sure who to see?">
          <div className="stack">
            <p className="muted">
              Describe your symptoms to the AI assistant for general guidance and a suggested
              specialist. It does not replace a medical diagnosis.
            </p>
            <Link to="/patient/assistant" className="button secondary">
              <Icon name="sparkles" size={18} /> Open AI assistant
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}

export function FindDoctorsPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get('q') ?? '');
  const debounced = useDebouncedValue(search.trim());
  const specializationId = Number(params.get('specialization')) || undefined;
  const page = Number(params.get('page')) || 1;
  const specializations = useSpecializations();
  const doctors = useDoctors({
    page,
    search: debounced || undefined,
    specialization_id: specializationId,
  });

  function update(next: Record<string, string | undefined>) {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value);
      else merged.delete(key);
    }
    setParams(merged, { replace: true });
  }

  return (
    <div className="stack">
      <PageHeader title="Find a doctor" description="Search by name or specialization." />
      <div className="filters">
        <label className="search-input">
          <Icon name="search" size={18} />
          <input
            type="search"
            placeholder="Search doctors or specializations"
            aria-label="Search doctors"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              update({ q: event.target.value || undefined, page: undefined });
            }}
          />
        </label>
        <SelectField
          label="Specialization"
          value={specializationId ?? ''}
          onChange={(event) =>
            update({ specialization: event.target.value || undefined, page: undefined })
          }
        >
          <option value="">All specializations</option>
          {specializations.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </SelectField>
      </div>
      <QueryState
        isLoading={doctors.isLoading}
        error={doctors.error}
        onRetry={() => void doctors.refetch()}
        isEmpty={!doctors.data?.items.length}
        empty={<EmptyState icon="stethoscope" title="No doctors match your search" />}
      >
        <div className="card-grid">
          {doctors.data?.items.map((doctor) => (
            <DoctorCard
              key={doctor.id}
              doctor={doctor}
              actions={
                <Link to={`/patient/doctors/${doctor.id}`} className="button small">
                  View availability
                </Link>
              }
            />
          ))}
        </div>
        <Pagination
          page={page}
          pages={doctors.data?.pages ?? 1}
          onChange={(p) => update({ page: String(p) })}
        />
      </QueryState>
    </div>
  );
}

export function DoctorProfilePage() {
  const id = Number(useParams().doctorId);
  const doctor = useDoctor(id);
  const careAppointments = useAppointments({ doctor_id: id, scope: 'all', page_size: 100 });
  const navigate = useNavigate();
  const openChat = useOpenConversation();
  const [booked, setBooked] = useState(false);
  const canMessage = booked || Boolean(careAppointments.data?.items.length);

  return (
    <div className="stack">
      <Link to="/patient/doctors" className="small-text">
        ← All doctors
      </Link>
      <QueryState isLoading={doctor.isLoading} error={doctor.error}>
        {doctor.data && (
          <div className="grid-2 align-start">
            <Card>
              <DoctorCard
                doctor={doctor.data}
                actions={
                  <button
                    type="button"
                    className="secondary small"
                    disabled={openChat.isPending || careAppointments.isLoading || !canMessage}
                    onClick={() =>
                      openChat.mutate(
                        { doctor_id: id },
                        { onSuccess: (c) => void navigate(`/patient/messages/${c.id}`) },
                      )
                    }
                  >
                    <Icon name="chat" size={16} /> {canMessage ? 'Message' : 'Book to message'}
                  </button>
                }
              />
              {openChat.isError && <Alert>{getErrorMessage(openChat.error)}</Alert>}
            </Card>
            <Card title="Book an appointment">
              {booked ? (
                <div className="stack">
                  <Alert tone="success">
                    Your appointment is booked. You'll find it under Appointments.
                  </Alert>
                  <div className="row wrap">
                    <Link to="/patient/appointments" className="button">
                      View appointments
                    </Link>
                    <button type="button" className="secondary" onClick={() => setBooked(false)}>
                      Book another
                    </button>
                  </div>
                </div>
              ) : (
                <BookingPanel doctorId={id} onBooked={() => setBooked(true)} />
              )}
            </Card>
          </div>
        )}
      </QueryState>
    </div>
  );
}

export function PatientAppointmentsPage() {
  const [scope, setScope] = useState<'upcoming' | 'past'>('upcoming');
  const [page, setPage] = useState(1);
  const appointments = useAppointments({ scope, page });
  return (
    <div className="stack">
      <PageHeader title="Appointments" />
      <Tabs
        tabs={[
          { value: 'upcoming', label: 'Upcoming' },
          { value: 'past', label: 'History' },
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
          empty={
            <EmptyState
              icon="calendar"
              title={scope === 'upcoming' ? 'No upcoming appointments' : 'No past appointments'}
            />
          }
        >
          <AppointmentList appointments={appointments.data?.items ?? []} perspective="patient" />
          <Pagination page={page} pages={appointments.data?.pages ?? 1} onChange={setPage} />
        </QueryState>
      </Card>
    </div>
  );
}

export function PatientMessagesPage() {
  const id = Number(useParams().conversationId) || null;
  return (
    <div className="stack fill">
      <PageHeader title="Messages" />
      <ChatView basePath="/patient/messages" conversationId={id} />
    </div>
  );
}

export function AssistantPage() {
  const id = Number(useParams().conversationId) || null;
  return (
    <div className="stack fill">
      <PageHeader
        title="AI health assistant"
        description="General information only — not a diagnosis. In an emergency, call emergency services."
      />
      <AssistantView conversationId={id} />
    </div>
  );
}
