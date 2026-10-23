import { useState } from 'react';
import { useNavigate } from 'react-router';

import { TextAreaField } from '@/components/FormField';
import { Icon } from '@/components/Icon';
import { Alert, Avatar, Modal, StatusBadge } from '@/components/ui';
import {
  useAppointmentPrescription,
} from '@/features/prescriptions';
import { getErrorMessage } from '@/lib/errors';
import { useClinicTimezone } from '@/lib/hooks';
import { formatDate, formatTime } from '@/lib/time';
import type { Appointment, AppointmentAction } from '@/lib/types';

import { useAppointmentAction } from './api';

type Perspective = 'patient' | 'doctor' | 'admin';

const ACTION_LABEL: Record<AppointmentAction, string> = {
  confirm: 'Confirm',
  cancel: 'Cancel',
  complete: 'Mark completed',
  no_show: 'No-show',
};

export function AppointmentList({
  appointments,
  perspective,
  showPrescription = false,
}: {
  appointments: Appointment[];
  perspective: Perspective;
  showPrescription?: boolean;
}) {
  const timeZone = useClinicTimezone();
  const action = useAppointmentAction();
  const [dialog, setDialog] = useState<{
    appointment: Appointment;
    action: 'cancel' | 'complete';
  } | null>(null);
  const [note, setNote] = useState('');

  function run(appointment: Appointment, kind: AppointmentAction) {
    if (kind === 'cancel' || kind === 'complete') {
      setNote('');
      setDialog({ appointment, action: kind });
      return;
    }
    action.mutate({ id: appointment.id, action: kind });
  }

  function confirmDialog() {
    if (!dialog) return;
    action.mutate(
      {
        id: dialog.appointment.id,
        action: dialog.action,
        reason: dialog.action === 'cancel' ? note || undefined : undefined,
        doctor_notes: dialog.action === 'complete' ? note || undefined : undefined,
      },
      { onSuccess: () => setDialog(null) },
    );
  }

  return (
    <>
      {action.isError && !dialog && <Alert>{getErrorMessage(action.error)}</Alert>}
      <ul className="appointment-list">
        {appointments.map((appointment) => {
          const counterpart =
            perspective === 'patient'
              ? { name: `Dr. ${appointment.doctor.full_name}`, url: appointment.doctor.avatar_url }
              : { name: appointment.patient.full_name, url: appointment.patient.avatar_url };
          return (
            <li key={appointment.id} className="appointment-row">
              <div className="appointment-when">
                <span className="appointment-time">
                  {formatTime(appointment.starts_at, timeZone)}
                </span>
                <span className="muted small-text">
                  {formatDate(appointment.starts_at, timeZone)}
                </span>
              </div>
              <div className="row appointment-who">
                <Avatar name={counterpart.name} url={counterpart.url} />
                <div>
                  <div className="strong">{counterpart.name}</div>
                  <div className="muted small-text">
                    {perspective === 'admin'
                      ? `with Dr. ${appointment.doctor.full_name}`
                      : appointment.doctor.specializations.join(', ')}
                  </div>
                  {appointment.reason && perspective !== 'patient' && (
                    <div className="small-text clamp">Reason: {appointment.reason}</div>
                  )}
                  {appointment.cancellation_reason && (
                    <div className="small-text muted">
                      Cancelled: {appointment.cancellation_reason}
                    </div>
                  )}
                </div>
              </div>
              <StatusBadge status={appointment.status} />
              <div className="row wrap appointment-actions">
                {appointment.allowed_actions.map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    className={
                      kind === 'cancel' || kind === 'no_show' ? 'secondary small' : 'small'
                    }
                    disabled={action.isPending}
                    onClick={() => run(appointment, kind)}
                  >
                    {ACTION_LABEL[kind]}
                  </button>
                ))}
                {showPrescription && appointment.status === 'COMPLETED' && (
                  <AppointmentPrescriptionButton
                    appointment={appointment}
                    perspective={perspective}
                  />
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <Modal
        open={dialog !== null}
        title={dialog?.action === 'cancel' ? 'Cancel appointment' : 'Complete appointment'}
        onClose={() => setDialog(null)}
        footer={
          <>
            <button type="button" className="secondary" onClick={() => setDialog(null)}>
              Back
            </button>
            <button
              type="button"
              className={dialog?.action === 'cancel' ? 'danger' : undefined}
              disabled={action.isPending}
              onClick={confirmDialog}
            >
              {dialog?.action === 'cancel' ? 'Cancel appointment' : 'Mark completed'}
            </button>
          </>
        }
      >
        {dialog && (
          <div className="stack">
            <p>
              {formatDate(dialog.appointment.starts_at, timeZone)} at{' '}
              {formatTime(dialog.appointment.starts_at, timeZone)}
            </p>
            {action.isError && <Alert>{getErrorMessage(action.error)}</Alert>}
            <TextAreaField
              label={dialog.action === 'cancel' ? 'Reason (optional)' : 'Visit notes (optional)'}
              value={note}
              maxLength={dialog.action === 'cancel' ? 500 : 4000}
              rows={4}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
        )}
      </Modal>
    </>
  );
}

function AppointmentPrescriptionButton({
  appointment,
  perspective,
}: {
  appointment: Appointment;
  perspective: Perspective;
}) {
  const navigate = useNavigate();
  const { data: rx, isLoading } = useAppointmentPrescription(appointment.id);
  const [emptyAlert, setEmptyAlert] = useState(false);

  function handleClick() {
    if (perspective === 'doctor') {
      if (rx) {
        navigate('/doctor/prescriptions');
      } else {
        navigate('/doctor/prescriptions/new', {
          state: {
            patientId: appointment.patient.id,
            patientName: appointment.patient.full_name,
            appointmentId: appointment.id,
            returnTo: '/doctor/appointments',
          },
        });
      }
    } else {
      if (rx) {
        navigate('/patient/prescriptions');
      } else {
        setEmptyAlert(true);
      }
    }
  }

  return (
    <>
      <button
        type="button"
        className="button secondary small"
        disabled={isLoading}
        onClick={handleClick}
        title={
          rx
            ? 'View digital prescription'
            : perspective === 'doctor'
              ? 'Issue prescription'
              : 'Prescription status'
        }
      >
        <Icon name="pill" size={14} />
        {rx ? 'Prescription' : perspective === 'doctor' ? '+ Issue Rx' : 'Prescription'}
      </button>

      <Modal
        open={emptyAlert}
        title="Prescription Status"
        onClose={() => setEmptyAlert(false)}
        footer={
          <button type="button" className="secondary" onClick={() => setEmptyAlert(false)}>
            Close
          </button>
        }
      >
        <p className="muted">
          No digital prescription was issued by Dr. {appointment.doctor.full_name} for this
          appointment. If you require medication or an updated prescription, please contact your
          doctor through Messages.
        </p>
      </Modal>
    </>
  );
}

