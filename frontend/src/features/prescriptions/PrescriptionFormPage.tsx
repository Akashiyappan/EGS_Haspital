import { useState, type FormEvent } from 'react';
import { useLocation, useNavigate } from 'react-router';

import { FormField, TextAreaField } from '@/components/FormField';
import { Icon } from '@/components/Icon';
import { Alert, Card, PageHeader } from '@/components/ui';
import { getErrorMessage } from '@/lib/errors';
import type { Prescription, PrescriptionCreatePayload, PrescriptionItem } from '@/lib/types';

import { useCreatePrescription, useFulfillPrescriptionRequest, useUpdatePrescription } from './api';

const COMMON_DIAGNOSES = [
  'Acute Upper Respiratory Infection',
  'Viral Bronchitis',
  'Essential Hypertension',
  'Type 2 Diabetes Mellitus',
  'Allergic Rhinitis',
  'Acute Gastroenteritis',
  'Migraine Headache',
  'Musculoskeletal Pain',
];

const COMMON_MEDICINES = [
  'Paracetamol 500mg',
  'Amoxicillin 500mg',
  'Azithromycin 500mg',
  'Cetirizine 10mg',
  'Pantoprazole 40mg',
  'Metformin 500mg',
  'Atorvastatin 10mg',
  'Ibuprofen 400mg',
];

const FREQUENCY_OPTIONS = [
  { value: '1-0-1 (Morning & Night)', label: '1-0-1 (Morning & Night)' },
  { value: '1-1-1 (Thrice daily)', label: '1-1-1 (Thrice daily)' },
  { value: '1-0-0 (Morning only)', label: '1-0-0 (Morning only)' },
  { value: '0-0-1 (Bedtime)', label: '0-0-1 (Bedtime)' },
  { value: '0-1-0 (Afternoon)', label: '0-1-0 (Afternoon)' },
  { value: 'SOS (As needed)', label: 'SOS (As needed)' },
];

const TIMING_OPTIONS = [
  { value: 'After food', label: 'After food' },
  { value: 'Before food', label: 'Before food' },
  { value: 'With meals', label: 'With meals' },
  { value: 'Empty stomach', label: 'Empty stomach' },
];

type DraftItem = Omit<PrescriptionItem, 'id'> & { tempId: string };

function defaultItem(): DraftItem {
  return {
    tempId: Math.random().toString(36).slice(2, 9),
    medicine_name: '',
    dosage: '1 tablet',
    frequency: '1-0-1 (Morning & Night)',
    timing: 'After food',
    duration_days: 5,
    instructions: '',
  };
}

interface PrescriptionFormRouteState {
  patientId: number;
  patientName?: string;
  appointmentId?: number | null;
  existingPrescription?: Prescription | null;
  requestId?: number;
  returnTo?: string;
}

export function PrescriptionFormPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const routeState = (location.state ?? {}) as Partial<PrescriptionFormRouteState>;
  const { patientId, patientName, appointmentId, existingPrescription, requestId, returnTo } = routeState;
  const createMutation = useCreatePrescription();
  const updateMutation = useUpdatePrescription();
  const fulfillRequest = useFulfillPrescriptionRequest();

  const [diagnosis, setDiagnosis] = useState(existingPrescription?.diagnosis ?? '');
  const [advice, setAdvice] = useState(existingPrescription?.advice ?? '');
  const [notes, setNotes] = useState(existingPrescription?.notes ?? '');
  const [followUpDate, setFollowUpDate] = useState(existingPrescription?.follow_up_date ?? '');
  const [items, setItems] = useState<DraftItem[]>(() => {
    if (existingPrescription?.items.length) {
      return existingPrescription.items.map((i) => ({
        tempId: Math.random().toString(36).slice(2, 9),
        medicine_name: i.medicine_name,
        dosage: i.dosage,
        frequency: i.frequency,
        timing: i.timing,
        duration_days: i.duration_days,
        instructions: i.instructions ?? '',
      }));
    }
    return [defaultItem()];
  });

  const isPending = createMutation.isPending || updateMutation.isPending || fulfillRequest.isPending;
  const error = createMutation.error || updateMutation.error;

  function addItem() {
    setItems((prev) => [...prev, defaultItem()]);
  }

  function removeItem(index: number) {
    if (items.length <= 1) return;
    setItems((prev) => prev.filter((_, i) => i !== index));
  }

  function updateItem(index: number, patch: Partial<DraftItem>) {
    setItems((prev) =>
      prev.map((item, i) => (i === index ? { ...item, ...patch } : item)),
    );
  }

  if (!patientId) {
    return <div className="stack"><PageHeader title="Prescription details missing" description="Choose a patient or open a prescription request to continue." /><button className="button secondary" onClick={() => navigate('/doctor/prescriptions')}>Back to prescriptions</button></div>;
  }
  const validPatientId = patientId;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!diagnosis.trim()) return;

    const payload: PrescriptionCreatePayload = {
      patient_id: validPatientId,
      appointment_id: appointmentId,
      diagnosis: diagnosis.trim(),
      advice: advice.trim() || undefined,
      notes: notes.trim() || undefined,
      follow_up_date: followUpDate || undefined,
      items: items.map((item) => ({
        medicine_name: item.medicine_name.trim(),
        dosage: item.dosage.trim(),
        frequency: item.frequency,
        timing: item.timing,
        duration_days: Number(item.duration_days) || 1,
        instructions: item.instructions?.trim() || null,
      })),
    };

    if (existingPrescription) {
      updateMutation.mutate(
        { id: existingPrescription.id, payload },
        {
          onSuccess: async () => {
            if (requestId) await fulfillRequest.mutateAsync(requestId);
            navigate(returnTo || '/doctor/prescriptions', { replace: true });
          },
        },
      );
    } else {
      createMutation.mutate(payload, {
        onSuccess: async () => {
          if (requestId) await fulfillRequest.mutateAsync(requestId);
          navigate(returnTo || '/doctor/prescriptions', { replace: true });
        },
      });
    }
  }

  return (
    <div className="stack">
      <PageHeader
        title={existingPrescription ? 'Update Prescription' : 'Issue Medical Prescription'}
        description="Add the diagnosis, medication instructions, and follow-up details for this patient."
        actions={<button type="button" className="button secondary" onClick={() => navigate(returnTo || '/doctor/prescriptions')}>Back</button>}
      />
      <Card>
      <form id="prescription-form" onSubmit={handleSubmit} className="stack">
        {patientName && (
          <div className="rx-form-patient-banner">
            <div>
              <span className="small-text muted">Patient:</span>{' '}
              <strong>{patientName}</strong>
            </div>
            {appointmentId && (
              <div>
                <span className="small-text muted">Linked Appointment:</span>{' '}
                <strong>#{appointmentId}</strong>
              </div>
            )}
          </div>
        )}

        {error && <Alert>{getErrorMessage(error)}</Alert>}
        {fulfillRequest.isError && <Alert>{getErrorMessage(fulfillRequest.error)}</Alert>}

        {/* Diagnosis with quick chips */}
        <div className="stack tight">
          <FormField
            label="Diagnosis / Primary Condition *"
            value={diagnosis}
            onChange={(e) => setDiagnosis(e.target.value)}
            placeholder="e.g. Acute Upper Respiratory Infection"
            required
          />
          <div className="rx-chips-row">
            <span className="small-text muted">Suggestions:</span>
            {COMMON_DIAGNOSES.slice(0, 4).map((d) => (
              <button
                key={d}
                type="button"
                className="rx-chip-button"
                onClick={() => setDiagnosis(d)}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        {/* Prescribed Medications */}
        <div className="stack tight">
          <div className="row justify-between align-center">
            <h3>Prescribed Medicines</h3>
            <button
              type="button"
              className="button secondary small"
              onClick={addItem}
            >
              <Icon name="plus" size={16} /> Add medicine
            </button>
          </div>

          <div className="rx-chips-row">
            <span className="small-text muted">Quick medicines:</span>
            {COMMON_MEDICINES.slice(0, 5).map((med) => (
              <button
                key={med}
                type="button"
                className="rx-chip-button"
                onClick={() => {
                  const lastIdx = items.length - 1;
                  if (!items[lastIdx]?.medicine_name) {
                    updateItem(lastIdx, { medicine_name: med });
                  } else {
                    setItems((prev) => [
                      ...prev,
                      { ...defaultItem(), medicine_name: med },
                    ]);
                  }
                }}
              >
                + {med}
              </button>
            ))}
          </div>

          <div className="rx-items-list stack">
            {items.map((item, idx) => (
              <div key={item.tempId} className="rx-item-card">
                <div className="row justify-between align-center rx-item-card-header">
                  <span className="badge small">Medicine #{idx + 1}</span>
                  {items.length > 1 && (
                    <button
                      type="button"
                      className="ghost icon-button danger small"
                      onClick={() => removeItem(idx)}
                      title="Remove medicine"
                    >
                      <Icon name="trash" size={16} />
                    </button>
                  )}
                </div>

                <div className="grid-2 align-start">
                  <FormField
                    label="Medicine Name & Strength *"
                    value={item.medicine_name}
                    placeholder="e.g. Amoxicillin 500mg"
                    onChange={(e) => updateItem(idx, { medicine_name: e.target.value })}
                    required
                  />
                  <FormField
                    label="Dosage *"
                    value={item.dosage}
                    placeholder="e.g. 1 tablet / 1 capsule / 5ml"
                    onChange={(e) => updateItem(idx, { dosage: e.target.value })}
                    required
                  />
                </div>

                <div className="grid-3 align-start">
                  <label className="form-field">
                    <span className="label-text">Frequency</span>
                    <select
                      className="input"
                      value={item.frequency}
                      onChange={(e) => updateItem(idx, { frequency: e.target.value })}
                    >
                      {FREQUENCY_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="form-field">
                    <span className="label-text">Timing</span>
                    <select
                      className="input"
                      value={item.timing}
                      onChange={(e) => updateItem(idx, { timing: e.target.value })}
                    >
                      {TIMING_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>

                  <FormField
                    label="Duration (days) *"
                    type="number"
                    min={1}
                    max={365}
                    value={item.duration_days.toString()}
                    onChange={(e) =>
                      updateItem(idx, { duration_days: Math.max(1, parseInt(e.target.value, 10) || 1) })
                    }
                    required
                  />
                </div>

                <FormField
                  label="Instructions / Precautions (optional)"
                  value={item.instructions ?? ''}
                  placeholder="e.g. Complete 5-day course, avoid alcohol"
                  onChange={(e) => updateItem(idx, { instructions: e.target.value })}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Advice and Notes */}
        <div className="grid-2 align-start">
          <TextAreaField
            label="Lifestyle & Dietary Advice (optional)"
            value={advice}
            placeholder="e.g. Drink plenty of warm fluids, steam inhalation twice daily."
            rows={3}
            onChange={(e) => setAdvice(e.target.value)}
          />
          <TextAreaField
            label="Clinical Notes (optional)"
            value={notes}
            placeholder="e.g. Chest clear on auscultation, follow-up if fever exceeds 101F."
            rows={3}
            onChange={(e) => setNotes(e.target.value)}
          />
        </div>

        <FormField
          label="Next Follow-up Date (optional)"
          type="date"
          value={followUpDate}
          onChange={(e) => setFollowUpDate(e.target.value)}
        />
        <div className="row justify-end gap-sm">
          <button type="button" className="secondary" onClick={() => navigate(returnTo || '/doctor/prescriptions')} disabled={isPending}>Cancel</button>
          <button
            type="submit"
            className="button"
            disabled={isPending || !diagnosis.trim() || items.some((i) => !i.medicine_name.trim())}
          >
            <Icon name="check" size={18} />
            {isPending ? 'Saving...' : existingPrescription ? 'Save Changes' : 'Issue Official Prescription'}
          </button>
        </div>
      </form>
      </Card>
    </div>
  );
}
