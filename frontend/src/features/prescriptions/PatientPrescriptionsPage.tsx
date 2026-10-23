import { useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { Icon } from '@/components/Icon';
import {
  Card,
  EmptyState,
  PageHeader,
  QueryState,
  StatCard,
  Tabs,
  Modal,
} from '@/components/ui';
import { useDoctors } from '@/features/doctors/api';
import { useOpenConversation } from '@/features/chat/api';
import { useClinicTimezone } from '@/lib/hooks';
import { formatDate } from '@/lib/time';
import { useCreatePrescriptionRequest, usePrescriptionRequests, usePrescriptions } from './api';

export function PatientPrescriptionsPage() {
  const timeZone = useClinicTimezone();
  const navigate = useNavigate();
  const openChat = useOpenConversation();

  const [filter, setFilter] = useState<'all' | 'active'>('all');
  const [requestOpen, setRequestOpen] = useState(false);
  const [doctorId, setDoctorId] = useState<number | ''>('');
  const [requestReason, setRequestReason] = useState('');
  const doctors = useDoctors({ page: 1 });
  const requestMutation = useCreatePrescriptionRequest();
  const requests = usePrescriptionRequests();

  const { data: prescriptions, isLoading, error, refetch } = usePrescriptions();

  const activePrescriptions = prescriptions?.filter((p) => p.is_active) ?? [];
  const displayList = filter === 'active' ? activePrescriptions : (prescriptions ?? []);

  // Compute active medication items for tracker
  const ongoingMedicines = activePrescriptions.flatMap((p) =>
    p.items.map((item) => ({
      ...item,
      doctorName: p.doctor.full_name,
      diagnosis: p.diagnosis,
      daysRemaining: p.days_remaining,
      prescriptionId: p.id,
    })),
  );

  return (
    <div className="stack">
      <PageHeader
        title="My Prescriptions & Medications"
        description="Review doctor-issued electronic prescriptions, dosage instructions, and track ongoing medication schedules."
        actions={
          <div className="row gap-sm"><Link to="/patient/doctors" className="button secondary"><Icon name="stethoscope" size={18} /> Consult a Doctor</Link><button className="button" onClick={() => setRequestOpen(true)}><Icon name="plus" size={18} /> Request Prescription</button></div>
        }
      />

      {requests.data?.map(request => <Card key={request.id}><strong>Prescription request {request.status.toLowerCase()}</strong><div className="small-text muted">For Dr. {request.doctor_name}: {request.reason}</div></Card>)}

      {/* Summary Stats */}
      <div className="stat-grid">
        <StatCard
          icon="pill"
          label="Active Prescriptions"
          value={activePrescriptions.length}
        />
        <StatCard
          icon="list"
          label="Total Prescriptions"
          value={prescriptions?.length ?? '–'}
        />
        <StatCard
          icon="sparkles"
          label="Ongoing Medicines"
          value={ongoingMedicines.length}
        />
      </div>

      {/* Active Medication Tracker Banner */}
      {ongoingMedicines.length > 0 && (
        <Card title="Today's Ongoing Medication Schedule">
          <div className="rx-tracker-container">
            <div className="rx-tracker-banner-header">
              <span className="badge success">
                <Icon name="check" size={14} /> Currently Active Treatment
              </span>
              <span className="small-text muted">
                Always take your prescribed dosage at the recommended intervals.
              </span>
            </div>

            <div className="rx-medicines-grid">
              {ongoingMedicines.map((med, idx) => (
                <div key={`${med.prescriptionId}-${idx}`} className="rx-med-card">
                  <div className="rx-med-card-top">
                    <div className="rx-med-icon-wrap">
                      <Icon name="pill" size={20} />
                    </div>
                    <div>
                      <div className="rx-med-name">{med.medicine_name}</div>
                      <div className="small-text muted">Prescribed by Dr. {med.doctorName}</div>
                    </div>
                  </div>

                  <div className="rx-med-pills-row">
                    <span className="rx-pill-badge dosage">{med.dosage}</span>
                    <span className="rx-pill-badge frequency">{med.frequency}</span>
                    <span className="rx-pill-badge timing">{med.timing}</span>
                  </div>

                  {med.instructions && (
                    <div className="rx-med-instructions small-text">
                      Note: {med.instructions}
                    </div>
                  )}

                  <div className="rx-med-footer">
                    <span className="small-text rx-days-tag">
                      {med.daysRemaining > 0
                        ? `${med.daysRemaining} days remaining (${med.duration_days} days total)`
                        : `Final day of treatment`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}

      {/* Filter Tabs */}
      <div className="row justify-between align-center">
        <Tabs
          tabs={[
            { value: 'all', label: `All Prescriptions (${prescriptions?.length ?? 0})` },
            { value: 'active', label: `Active (${activePrescriptions.length})` },
          ]}
          value={filter}
          onChange={(val) => setFilter(val as 'all' | 'active')}
        />
      </div>

      {/* Prescription Cards */}
      <QueryState
        isLoading={isLoading}
        error={error}
        onRetry={() => void refetch()}
        isEmpty={displayList.length === 0}
        empty={
          <EmptyState
            icon="pill"
            title={filter === 'active' ? 'No active prescriptions' : 'No prescriptions yet'}
            description="Prescriptions issued by your doctors after appointments will appear here."
            action={
              <Link to="/patient/doctors" className="button small">
                Find a doctor
              </Link>
            }
          />
        }
      >
        <div className="stack">
          {displayList.map((prescription) => (
            <Card key={prescription.id}>
              <div className="stack rx-card-body">
                {/* Header: Doctor & Date */}
                <div className="row justify-between align-center wrap gap-md">
                  <div className="row align-center gap-md">
                    <div className="avatar-placeholder">
                      <Icon name="stethoscope" size={22} />
                    </div>
                    <div>
                      <div className="strong">Dr. {prescription.doctor.full_name}</div>
                      <div className="small-text muted">
                        {prescription.doctor.specializations.join(' · ') || 'Specialist'} ·{' '}
                        {formatDate(prescription.created_at, timeZone)}
                      </div>
                    </div>
                  </div>

                  <div className="row align-center gap-sm">
                    {prescription.is_active ? (
                      <span className="badge success">Active ({prescription.days_remaining}d left)</span>
                    ) : (
                      <span className="badge muted">Completed Course</span>
                    )}
                    <span className="badge small">RX-{prescription.id.toString().padStart(6, '0')}</span>
                  </div>
                </div>

                {/* Diagnosis Banner */}
                <div className="rx-card-diagnosis">
                  <span className="rx-symbol">℞</span>
                  <div>
                    <span className="small-text muted">Diagnosis:</span>
                    <strong className="rx-card-diagnosis-title"> {prescription.diagnosis}</strong>
                  </div>
                </div>

                {/* Medicines List Preview */}
                <div className="rx-card-medicines-table-wrap">
                  <table className="table rx-card-table">
                    <thead>
                      <tr>
                        <th>Medicine</th>
                        <th>Dosage</th>
                        <th>Frequency</th>
                        <th>Timing</th>
                        <th>Duration</th>
                      </tr>
                    </thead>
                    <tbody>
                      {prescription.items.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <strong>{item.medicine_name}</strong>
                            {item.instructions && (
                              <div className="small-text muted">{item.instructions}</div>
                            )}
                          </td>
                          <td>{item.dosage}</td>
                          <td>
                            <span className="rx-pill-badge">{item.frequency}</span>
                          </td>
                          <td>{item.timing}</td>
                          <td>{item.duration_days} days</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Advice or follow-up */}
                {(prescription.advice || prescription.follow_up_date) && (
                  <div className="row justify-between align-center wrap gap-sm rx-card-subinfo">
                    {prescription.advice && (
                      <div className="small-text">
                        <strong>Advice:</strong> {prescription.advice}
                      </div>
                    )}
                    {prescription.follow_up_date && (
                      <div className="small-text rx-follow-badge">
                        <Icon name="calendar" size={14} /> Follow-up recommended: {prescription.follow_up_date}
                      </div>
                    )}
                  </div>
                )}

                {/* Actions Footer */}
                <div className="row justify-end align-center gap-sm rx-card-actions">
                  <button
                    type="button"
                    className="button secondary small"
                    onClick={() =>
                      openChat.mutate(
                        { doctor_id: prescription.doctor.id },
                        { onSuccess: (c) => void navigate(`/patient/messages/${c.id}`) },
                      )
                    }
                  >
                    <Icon name="chat" size={16} /> Message Doctor
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      </QueryState>

      <Modal open={requestOpen} title="Request a Prescription" onClose={() => setRequestOpen(false)} footer={<div className="row justify-end gap-sm"><button className="secondary" onClick={() => setRequestOpen(false)}>Cancel</button><button className="button" disabled={!doctorId || requestReason.trim().length < 3 || requestMutation.isPending} onClick={() => requestMutation.mutate({ doctor_id: Number(doctorId), reason: requestReason }, { onSuccess: () => { setRequestOpen(false); setRequestReason(''); } })}>Send Request</button></div>}>
        <div className="stack"><p className="muted">Choose the doctor who should review your request. The doctor will decide whether to issue a prescription.</p><label className="form-field"><span className="label-text">Doctor</span><select className="input" value={doctorId} onChange={e => setDoctorId(e.target.value ? Number(e.target.value) : '')}><option value="">Select a doctor</option>{doctors.data?.items.map(d => <option key={d.id} value={d.id}>Dr. {d.full_name}</option>)}</select></label><label className="form-field"><span className="label-text">What do you need reviewed?</span><textarea className="input" rows={4} value={requestReason} onChange={e => setRequestReason(e.target.value)} placeholder="Describe your symptoms or medication request" /></label>{requestMutation.isError && <p className="error-text">Could not send your request. Please try again.</p>}</div>
      </Modal>
    </div>
  );
}
