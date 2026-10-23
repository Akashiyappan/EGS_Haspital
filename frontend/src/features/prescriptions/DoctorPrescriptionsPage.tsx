import { useState } from 'react';
import { useNavigate } from 'react-router';

import { Icon } from '@/components/Icon';
import {
  Card,
  EmptyState,
  PageHeader,
  QueryState,
  StatCard,
} from '@/components/ui';
import { useClinicTimezone } from '@/lib/hooks';
import { formatDate } from '@/lib/time';
import { useDeletePrescription, usePrescriptionRequests, usePrescriptions } from './api';

export function DoctorPrescriptionsPage() {
  const timeZone = useClinicTimezone();
  const navigate = useNavigate();
  const deleteMutation = useDeletePrescription();

  const [search, setSearch] = useState('');
  const requests = usePrescriptionRequests();

  const { data: prescriptions, isLoading, error, refetch } = usePrescriptions();

  const filtered = prescriptions?.filter((p) => {
    if (!search.trim()) return true;
    const term = search.toLowerCase();
    return (
      p.patient.full_name.toLowerCase().includes(term) ||
      p.diagnosis.toLowerCase().includes(term) ||
      p.items.some((i) => i.medicine_name.toLowerCase().includes(term))
    );
  }) ?? [];

  const activeCount = prescriptions?.filter((p) => p.is_active).length ?? 0;

  function handleDelete(id: number) {
    if (window.confirm('Are you sure you want to delete this prescription?')) {
      deleteMutation.mutate(id);
    }
  }

  return (
    <div className="stack">
      <PageHeader
        title="Prescriptions Management"
        description="Issue, review, and manage digital e-prescriptions for your patients."
        actions={<span className="badge muted">Prescriptions are issued after reviewing a patient request or appointment</span>}
      />

      {/* Stats */}
      <Card title="Patient Requests">
        {!requests.data?.filter(r => r.status === 'PENDING').length ? <p className="muted">No prescription requests waiting for review.</p> : <div className="stack">{requests.data.filter(r => r.status === 'PENDING').map(request => <div key={request.id} className="row justify-between align-center wrap"><div><strong>{request.patient_name}</strong><div className="small-text muted">{request.reason}</div></div><button className="button small" onClick={() => navigate('/doctor/prescriptions/new', { state: { patientId: request.patient_id, patientName: request.patient_name, appointmentId: request.appointment_id, requestId: request.id, returnTo: '/doctor/prescriptions' } })}>Review & prescribe</button></div>)}</div>}
      </Card>

      <div className="stat-grid">
        <StatCard
          icon="pill"
          label="Prescriptions Issued"
          value={prescriptions?.length ?? '–'}
        />
        <StatCard
          icon="check"
          label="Currently Active Courses"
          value={activeCount}
        />
        <StatCard
          icon="users"
          label="Patients Prescribed"
          value={
            prescriptions
              ? new Set(prescriptions.map((p) => p.patient_id)).size
              : '–'
          }
        />
      </div>

      {/* Search Input */}
      <div className="row justify-between align-center wrap gap-md">
        <label className="search-input" style={{ maxWidth: '400px', flex: 1 }}>
          <Icon name="search" size={18} />
          <input
            type="search"
            placeholder="Search by patient name, diagnosis, or medicine..."
            aria-label="Search prescriptions"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>

      {/* Prescriptions List */}
      <Card>
        <QueryState
          isLoading={isLoading}
          error={error}
          onRetry={() => void refetch()}
          isEmpty={filtered.length === 0}
          empty={
            <EmptyState
              icon="pill"
              title={search ? 'No prescriptions match your search' : 'No prescriptions issued yet'}
              description="Patient requests appear above. You can also issue a prescription from a completed appointment."
            />
          }
        >
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Patient</th>
                  <th scope="col">Diagnosis</th>
                  <th scope="col">Medicines Prescribed</th>
                  <th scope="col">Status</th>
                  <th scope="col" style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((rx) => (
                  <tr key={rx.id}>
                    <td>
                      <div className="strong">{formatDate(rx.created_at, timeZone)}</div>
                      <div className="small-text muted">RX-{rx.id.toString().padStart(6, '0')}</div>
                    </td>
                    <td>
                      <div className="strong">{rx.patient.full_name}</div>
                      <div className="small-text muted">{rx.patient.email}</div>
                    </td>
                    <td>
                      <div className="rx-card-diagnosis-title strong">{rx.diagnosis}</div>
                      {rx.follow_up_date && (
                        <div className="small-text rx-follow-badge">
                          Follow-up: {rx.follow_up_date}
                        </div>
                      )}
                    </td>
                    <td>
                      <div className="small-text">
                        {rx.items.map((item) => (
                          <div key={item.id} className="rx-item-summary-line">
                            • <strong>{item.medicine_name}</strong> ({item.dosage}, {item.frequency})
                          </div>
                        ))}
                      </div>
                    </td>
                    <td>
                      {rx.is_active ? (
                        <span className="badge success">Active ({rx.days_remaining}d left)</span>
                      ) : (
                        <span className="badge muted">Completed</span>
                      )}
                    </td>
                    <td>
                      <div className="row justify-end align-center gap-xs">
                        <button
                          type="button"
                          className="button secondary small"
                          title="Edit Prescription"
                          onClick={() => navigate('/doctor/prescriptions/new', { state: { patientId: rx.patient_id, patientName: rx.patient.full_name, appointmentId: rx.appointment_id, existingPrescription: rx, returnTo: '/doctor/prescriptions' } })}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="ghost icon-button danger small"
                          title="Delete"
                          disabled={deleteMutation.isPending}
                          onClick={() => handleDelete(rx.id)}
                        >
                          <Icon name="trash" size={16} />
                        </button>
                      </div>
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
