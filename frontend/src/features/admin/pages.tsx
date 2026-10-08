import { type FormEvent, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';

import { FormField, SelectField } from '@/components/FormField';
import { Icon } from '@/components/Icon';
import {
  Alert,
  Avatar,
  Badge,
  Card,
  EmptyState,
  Modal,
  PageHeader,
  Pagination,
  QueryState,
  StatCard,
  Tabs,
} from '@/components/ui';
import { useAppointments } from '@/features/appointments/api';
import { AppointmentList } from '@/features/appointments/AppointmentList';
import { useSpecializations } from '@/features/doctors/api';
import { AvatarUploader } from '@/pages/ProfilePage';
import { getErrorMessage } from '@/lib/errors';
import { useClinicTimezone, useDebouncedValue } from '@/lib/hooks';
import { formatDateTime, zonedToday } from '@/lib/time';
import type { AppointmentStatus, Role } from '@/lib/types';
import { validatePassword } from '@/lib/validation';

import {
  useAdminDoctor,
  useAdminDoctors,
  useAdminSpecializations,
  useAdminStats,
  useAdminUsers,
  useAuditLogs,
  useDeleteDoctor,
  useDoctorStatus,
  useResetDoctorPassword,
  useSaveSpecialization,
  useUploadDoctorAvatar,
  useUserStatus,
} from './api';
import { DoctorForm } from './DoctorForm';
import { ScheduleEditor } from './ScheduleEditor';
import { TimeOffManager } from './TimeOffManager';

export function AdminDashboard() {
  const stats = useAdminStats();
  const timeZone = useClinicTimezone();
  const today = zonedToday(timeZone);
  const todays = useAppointments({ date_from: today, date_to: today, page_size: 10 });
  return (
    <div className="stack">
      <PageHeader
        title="Administration"
        actions={
          <Link to="/admin/doctors/new" className="button">
            <Icon name="plus" size={18} /> Add doctor
          </Link>
        }
      />
      <QueryState isLoading={stats.isLoading} error={stats.error}>
        {stats.data && (
          <div className="stat-grid">
            <StatCard icon="stethoscope" label="Active doctors" value={stats.data.doctors_active} />
            <StatCard icon="users" label="Patients" value={stats.data.patients} />
            <StatCard
              icon="calendar"
              label="Appointments today"
              value={stats.data.appointments_today}
            />
            <StatCard
              icon="list"
              label="Upcoming appointments"
              value={stats.data.appointments_upcoming}
            />
          </div>
        )}
      </QueryState>
      <Card title="Today's appointments" actions={<Link to="/admin/appointments">View all</Link>}>
        <QueryState
          isLoading={todays.isLoading}
          error={todays.error}
          isEmpty={!todays.data?.items.length}
          empty={<EmptyState icon="calendar" title="No appointments today" />}
        >
          <AppointmentList appointments={todays.data?.items ?? []} perspective="admin" />
        </QueryState>
      </Card>
    </div>
  );
}

export function AdminDoctorsPage() {
  const [search, setSearch] = useState('');
  const [specializationId, setSpecializationId] = useState<number>();
  const [status, setStatus] = useState<'' | 'active' | 'inactive'>('');
  const [page, setPage] = useState(1);
  const debounced = useDebouncedValue(search.trim());
  const specializations = useSpecializations();
  const doctors = useAdminDoctors({
    page,
    search: debounced || undefined,
    specialization_id: specializationId,
    is_active: status === '' ? undefined : status === 'active',
  });

  return (
    <div className="stack">
      <PageHeader
        title="Doctors"
        actions={
          <Link to="/admin/doctors/new" className="button">
            <Icon name="plus" size={18} /> Add doctor
          </Link>
        }
      />
      <div className="filters">
        <label className="search-input">
          <Icon name="search" size={18} />
          <input
            type="search"
            placeholder="Search name, email or specialization"
            aria-label="Search doctors"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </label>
        <SelectField
          label="Specialization"
          value={specializationId ?? ''}
          onChange={(e) => {
            setSpecializationId(Number(e.target.value) || undefined);
            setPage(1);
          }}
        >
          <option value="">All</option>
          {specializations.data?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as typeof status);
            setPage(1);
          }}
        >
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="inactive">Inactive</option>
        </SelectField>
      </div>
      <Card>
        <QueryState
          isLoading={doctors.isLoading}
          error={doctors.error}
          isEmpty={!doctors.data?.items.length}
          empty={<EmptyState icon="stethoscope" title="No doctors found" />}
        >
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Doctor</th>
                  <th scope="col">Specializations</th>
                  <th scope="col">Experience</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {doctors.data?.items.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <Link to={`/admin/doctors/${d.id}`} className="row">
                        <Avatar name={d.full_name} url={d.avatar_url} size={32} />
                        <span>
                          Dr. {d.full_name}
                          <span className="muted small-text block">{d.email}</span>
                        </span>
                      </Link>
                    </td>
                    <td>{d.specializations.map((s) => s.name).join(', ')}</td>
                    <td>{d.experience_years} yrs</td>
                    <td>
                      {d.is_active ? (
                        <Badge tone="success">Active</Badge>
                      ) : (
                        <Badge tone="danger">Inactive</Badge>
                      )}
                      {d.must_change_password && <Badge tone="warning">Temp password</Badge>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pages={doctors.data?.pages ?? 1} onChange={setPage} />
        </QueryState>
      </Card>
    </div>
  );
}

export function AdminNewDoctorPage() {
  const navigate = useNavigate();
  return (
    <div className="stack">
      <Link to="/admin/doctors" className="small-text">
        ← Doctors
      </Link>
      <PageHeader title="Add doctor" description="Creates the doctor's login and profile." />
      <Card>
        <DoctorForm
          onSaved={(doctor) => void navigate(`/admin/doctors/${doctor.id}?tab=schedule`)}
        />
      </Card>
    </div>
  );
}

type DoctorTab = 'profile' | 'schedule' | 'timeoff' | 'appointments' | 'account';

export function AdminDoctorDetailPage() {
  const id = Number(useParams().doctorId);
  const initialTab =
    (new URLSearchParams(window.location.search).get('tab') as DoctorTab) || 'profile';
  const [tab, setTab] = useState<DoctorTab>(initialTab);
  const doctor = useAdminDoctor(id);
  const avatar = useUploadDoctorAvatar(id);
  const [saved, setSaved] = useState(false);

  return (
    <div className="stack">
      <Link to="/admin/doctors" className="small-text">
        ← Doctors
      </Link>
      <QueryState isLoading={doctor.isLoading} error={doctor.error}>
        {doctor.data && (
          <>
            <PageHeader
              title={`Dr. ${doctor.data.full_name}`}
              description={doctor.data.specializations.map((s) => s.name).join(' · ')}
              actions={
                doctor.data.is_active ? (
                  <Badge tone="success">Active</Badge>
                ) : (
                  <Badge tone="danger">Inactive</Badge>
                )
              }
            />
            <Tabs
              tabs={[
                { value: 'profile', label: 'Profile' },
                { value: 'schedule', label: 'Schedule' },
                { value: 'timeoff', label: 'Time off' },
                { value: 'appointments', label: 'Appointments' },
                { value: 'account', label: 'Account' },
              ]}
              value={tab}
              onChange={setTab}
            />
            {tab === 'profile' && (
              <Card>
                <div className="stack">
                  <AvatarUploader
                    name={doctor.data.full_name}
                    url={doctor.data.avatar_url}
                    onUpload={(file) => avatar.mutate(file)}
                    pending={avatar.isPending}
                    error={avatar.error}
                  />
                  {saved && <Alert tone="success">Saved.</Alert>}
                  <DoctorForm
                    key={doctor.dataUpdatedAt}
                    doctor={doctor.data}
                    onSaved={() => setSaved(true)}
                  />
                </div>
              </Card>
            )}
            {tab === 'schedule' && (
              <Card title="Weekly schedule">
                <ScheduleEditor doctorId={id} />
              </Card>
            )}
            {tab === 'timeoff' && (
              <Card title="Leave & unavailability">
                <TimeOffManager doctorId={id} />
              </Card>
            )}
            {tab === 'appointments' && <DoctorAppointments doctorId={id} />}
            {tab === 'account' && <DoctorAccount doctorId={id} isActive={doctor.data.is_active} />}
          </>
        )}
      </QueryState>
    </div>
  );
}

function DoctorAppointments({ doctorId }: { doctorId: number }) {
  const [scope, setScope] = useState<'upcoming' | 'past'>('upcoming');
  const [page, setPage] = useState(1);
  const appointments = useAppointments({ doctor_id: doctorId, scope, page });
  return (
    <Card
      title="Appointments"
      actions={
        <Tabs
          tabs={[
            { value: 'upcoming', label: 'Upcoming' },
            { value: 'past', label: 'Past' },
          ]}
          value={scope}
          onChange={(v) => {
            setScope(v);
            setPage(1);
          }}
        />
      }
    >
      <QueryState
        isLoading={appointments.isLoading}
        error={appointments.error}
        isEmpty={!appointments.data?.items.length}
        empty={<EmptyState icon="calendar" title="No appointments" />}
      >
        <AppointmentList appointments={appointments.data?.items ?? []} perspective="admin" />
        <Pagination page={page} pages={appointments.data?.pages ?? 1} onChange={setPage} />
      </QueryState>
    </Card>
  );
}

function DoctorAccount({ doctorId, isActive }: { doctorId: number; isActive: boolean }) {
  const navigate = useNavigate();
  const status = useDoctorStatus(doctorId);
  const reset = useResetDoctorPassword(doctorId);
  const remove = useDeleteDoctor(doctorId);
  const [confirm, setConfirm] = useState<'deactivate' | 'delete' | null>(null);
  const [reason, setReason] = useState('');
  const [password, setPassword] = useState('');
  const [passwordError, setPasswordError] = useState<string>();

  function resetPassword(event: FormEvent) {
    event.preventDefault();
    const invalid = validatePassword(password);
    setPasswordError(invalid);
    if (!invalid) reset.mutate(password, { onSuccess: () => setPassword('') });
  }

  return (
    <div className="stack">
      <Card title="Status">
        <div className="stack">
          {status.data && (
            <Alert tone="success">
              Status updated. {status.data.cancelled_appointments} upcoming appointment(s) were
              cancelled and patients notified.
            </Alert>
          )}
          {status.isError && <Alert>{getErrorMessage(status.error)}</Alert>}
          {isActive ? (
            <button type="button" className="danger" onClick={() => setConfirm('deactivate')}>
              Deactivate doctor
            </button>
          ) : (
            <button type="button" onClick={() => status.mutate({ is_active: true })}>
              Reactivate doctor
            </button>
          )}
        </div>
      </Card>
      <Card title="Reset password">
        <form className="stack" onSubmit={resetPassword} noValidate>
          {reset.isSuccess && (
            <Alert tone="success">Temporary password set. The doctor has been signed out.</Alert>
          )}
          {reset.isError && <Alert>{getErrorMessage(reset.error)}</Alert>}
          <FormField
            label="New temporary password"
            type="password"
            autoComplete="new-password"
            value={password}
            error={passwordError}
            hint="The doctor must change it at next sign-in."
            onChange={(e) => setPassword(e.target.value)}
          />
          <div className="row">
            <button type="submit" className="secondary" disabled={reset.isPending}>
              Set temporary password
            </button>
          </div>
        </form>
      </Card>
      <Card title="Remove doctor">
        <p className="muted">
          Removes the doctor from the directory and cancels upcoming appointments. Records are kept.
        </p>
        <button type="button" className="danger" onClick={() => setConfirm('delete')}>
          Remove doctor
        </button>
        {remove.isError && <Alert>{getErrorMessage(remove.error)}</Alert>}
      </Card>
      <Modal
        open={confirm !== null}
        title={confirm === 'delete' ? 'Remove doctor?' : 'Deactivate doctor?'}
        onClose={() => setConfirm(null)}
        footer={
          <>
            <button type="button" className="secondary" onClick={() => setConfirm(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="danger"
              disabled={status.isPending || remove.isPending}
              onClick={() => {
                if (confirm === 'delete') {
                  remove.mutate(undefined, { onSuccess: () => void navigate('/admin/doctors') });
                } else {
                  status.mutate(
                    { is_active: false, reason: reason.trim() || undefined },
                    { onSuccess: () => setConfirm(null) },
                  );
                }
              }}
            >
              {confirm === 'delete' ? 'Remove' : 'Deactivate'}
            </button>
          </>
        }
      >
        <div className="stack">
          <p>All upcoming appointments with this doctor will be cancelled and patients notified.</p>
          {confirm === 'deactivate' && (
            <FormField
              label="Reason shown to patients (optional)"
              value={reason}
              maxLength={255}
              onChange={(e) => setReason(e.target.value)}
            />
          )}
        </div>
      </Modal>
    </div>
  );
}

export function AdminAppointmentsPage() {
  const [status, setStatus] = useState<AppointmentStatus | ''>('');
  const [doctorId, setDoctorId] = useState<number>();
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [page, setPage] = useState(1);
  const doctors = useAdminDoctors({ page: 1 });
  const appointments = useAppointments({
    page,
    status: status || undefined,
    doctor_id: doctorId,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  });

  return (
    <div className="stack">
      <PageHeader title="Appointments" description="All appointments across the clinic." />
      <div className="filters">
        <SelectField
          label="Doctor"
          value={doctorId ?? ''}
          onChange={(e) => {
            setDoctorId(Number(e.target.value) || undefined);
            setPage(1);
          }}
        >
          <option value="">All doctors</option>
          {doctors.data?.items.map((d) => (
            <option key={d.id} value={d.id}>
              Dr. {d.full_name}
            </option>
          ))}
        </SelectField>
        <SelectField
          label="Status"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value as AppointmentStatus | '');
            setPage(1);
          }}
        >
          <option value="">Any</option>
          {['BOOKED', 'CONFIRMED', 'COMPLETED', 'CANCELLED', 'NO_SHOW'].map((s) => (
            <option key={s} value={s}>
              {s.replace('_', ' ').toLowerCase()}
            </option>
          ))}
        </SelectField>
        <FormField
          label="From"
          type="date"
          value={dateFrom}
          onChange={(e) => {
            setDateFrom(e.target.value);
            setPage(1);
          }}
        />
        <FormField
          label="To"
          type="date"
          value={dateTo}
          onChange={(e) => {
            setDateTo(e.target.value);
            setPage(1);
          }}
        />
      </div>
      <Card>
        <QueryState
          isLoading={appointments.isLoading}
          error={appointments.error}
          isEmpty={!appointments.data?.items.length}
          empty={<EmptyState icon="calendar" title="No appointments match" />}
        >
          <AppointmentList appointments={appointments.data?.items ?? []} perspective="admin" />
          <Pagination page={page} pages={appointments.data?.pages ?? 1} onChange={setPage} />
        </QueryState>
      </Card>
    </div>
  );
}

export function AdminSpecializationsPage() {
  const specializations = useAdminSpecializations();
  const save = useSaveSpecialization();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  function submit(event: FormEvent) {
    event.preventDefault();
    if (name.trim().length < 2) return;
    save.mutate(
      { name: name.trim(), description: description.trim() || null },
      {
        onSuccess: () => {
          setName('');
          setDescription('');
        },
      },
    );
  }

  return (
    <div className="stack">
      <PageHeader
        title="Specializations"
        description="Used for doctor search and by the AI assistant to suggest the right specialist."
      />
      <Card title="Add specialization">
        <form className="stack" onSubmit={submit}>
          {save.isError && <Alert>{getErrorMessage(save.error)}</Alert>}
          <div className="grid-2">
            <FormField
              label="Name"
              value={name}
              maxLength={100}
              onChange={(e) => setName(e.target.value)}
            />
            <FormField
              label="Description"
              hint="Helps patients and the AI assistant understand what it covers."
              value={description}
              maxLength={1000}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="row">
            <button type="submit" disabled={save.isPending || name.trim().length < 2}>
              Add
            </button>
          </div>
        </form>
      </Card>
      <Card>
        <QueryState isLoading={specializations.isLoading} error={specializations.error}>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Description</th>
                  <th scope="col">Status</th>
                  <th scope="col" />
                </tr>
              </thead>
              <tbody>
                {specializations.data?.map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}</td>
                    <td className="muted">{s.description}</td>
                    <td>
                      {s.is_active ? (
                        <Badge tone="success">Active</Badge>
                      ) : (
                        <Badge tone="neutral">Hidden</Badge>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="secondary small"
                        onClick={() => save.mutate({ id: s.id, is_active: !s.is_active })}
                      >
                        {s.is_active ? 'Hide' : 'Show'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </QueryState>
      </Card>
    </div>
  );
}

export function AdminUsersPage() {
  const timeZone = useClinicTimezone();
  const [role, setRole] = useState<Role | ''>('PATIENT');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const debounced = useDebouncedValue(search.trim());
  const users = useAdminUsers({ page, role: role || undefined, search: debounced || undefined });
  const status = useUserStatus();

  return (
    <div className="stack">
      <PageHeader title="Users" description="Patient and administrator accounts." />
      <div className="filters">
        <label className="search-input">
          <Icon name="search" size={18} />
          <input
            type="search"
            aria-label="Search users"
            placeholder="Search name or email"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </label>
        <SelectField
          label="Role"
          value={role}
          onChange={(e) => {
            setRole(e.target.value as Role | '');
            setPage(1);
          }}
        >
          <option value="">All</option>
          <option value="PATIENT">Patients</option>
          <option value="DOCTOR">Doctors</option>
          <option value="ADMIN">Admins</option>
        </SelectField>
      </div>
      {status.isError && <Alert>{getErrorMessage(status.error)}</Alert>}
      <Card>
        <QueryState
          isLoading={users.isLoading}
          error={users.error}
          isEmpty={!users.data?.items.length}
          empty={<EmptyState icon="users" title="No users found" />}
        >
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">Role</th>
                  <th scope="col">Last sign-in</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {users.data?.items.map((u) => (
                  <tr key={u.id}>
                    <td>
                      {u.full_name}
                      <span className="muted small-text block">{u.email}</span>
                    </td>
                    <td>{u.role.toLowerCase()}</td>
                    <td>{u.last_login_at ? formatDateTime(u.last_login_at, timeZone) : '–'}</td>
                    <td>
                      {u.role === 'DOCTOR' ? (
                        <span className="muted small-text">Manage under Doctors</span>
                      ) : (
                        <button
                          type="button"
                          className={u.is_active ? 'secondary small' : 'small'}
                          disabled={status.isPending}
                          onClick={() => status.mutate({ id: u.id, is_active: !u.is_active })}
                        >
                          {u.is_active ? 'Deactivate' : 'Activate'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pages={users.data?.pages ?? 1} onChange={setPage} />
        </QueryState>
      </Card>
    </div>
  );
}

export function AdminHolidaysPage() {
  return (
    <div className="stack">
      <PageHeader
        title="Clinic holidays"
        description="Closures that block appointments for every doctor."
      />
      <Card>
        <TimeOffManager doctorId="clinic" />
      </Card>
    </div>
  );
}

export function AdminAuditPage() {
  const timeZone = useClinicTimezone();
  const [action, setAction] = useState('');
  const [page, setPage] = useState(1);
  const logs = useAuditLogs({ page, action: action || undefined });
  return (
    <div className="stack">
      <PageHeader title="Audit log" description="Security-sensitive and administrative actions." />
      <div className="filters">
        <SelectField
          label="Action"
          value={action}
          onChange={(e) => {
            setAction(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All actions</option>
          {[
            'auth.login_succeeded',
            'auth.login_failed',
            'auth.password_changed',
            'doctor.created',
            'doctor.updated',
            'doctor.deactivated',
            'schedule.changed',
            'time_off.added',
            'appointment.booked',
            'appointment.status_changed',
            'user.deactivated',
          ].map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </SelectField>
      </div>
      <Card>
        <QueryState
          isLoading={logs.isLoading}
          error={logs.error}
          isEmpty={!logs.data?.items.length}
          empty={<EmptyState icon="shield" title="No entries" />}
        >
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Action</th>
                  <th scope="col">Actor</th>
                  <th scope="col">Entity</th>
                  <th scope="col">Details</th>
                </tr>
              </thead>
              <tbody>
                {logs.data?.items.map((log) => (
                  <tr key={log.id}>
                    <td>{formatDateTime(log.created_at, timeZone)}</td>
                    <td>
                      <code>{log.action}</code>
                    </td>
                    <td>{log.actor_id ?? '–'}</td>
                    <td>{log.entity_type ? `${log.entity_type} #${log.entity_id}` : '–'}</td>
                    <td className="small-text muted">
                      <code>{JSON.stringify(log.details)}</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={page} pages={logs.data?.pages ?? 1} onChange={setPage} />
        </QueryState>
      </Card>
    </div>
  );
}
