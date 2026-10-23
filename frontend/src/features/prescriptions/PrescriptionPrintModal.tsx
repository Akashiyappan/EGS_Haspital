import { Icon } from '@/components/Icon';
import { Modal } from '@/components/ui';
import { useClinicTimezone } from '@/lib/hooks';
import { formatDate } from '@/lib/time';
import type { Prescription } from '@/lib/types';

interface PrescriptionPrintModalProps {
  prescription: Prescription | null;
  open: boolean;
  onClose: () => void;
}

export function PrescriptionPrintModal({
  prescription,
  open,
  onClose,
}: PrescriptionPrintModalProps) {
  const timeZone = useClinicTimezone();

  if (!prescription) return null;

  function handlePrint() {
    window.print();
  }

  return (
    <Modal
      open={open}
      title="Medical Prescription"
      onClose={onClose}
      footer={
        <div className="row wrap justify-between fill-width print-hide">
          <button type="button" className="secondary" onClick={onClose}>
            Close
          </button>
          <button type="button" className="button" onClick={handlePrint}>
            <Icon name="printer" size={18} /> Print / Save as PDF
          </button>
        </div>
      }
    >
      <div className="prescription-document" id={`rx-${prescription.id}`}>
        {/* Hospital Letterhead Header */}
        <div className="rx-header">
          <div className="rx-hospital-brand">
            <div className="rx-logo-box">
              <Icon name="shield" size={28} />
            </div>
            <div>
              <h2 className="rx-hospital-name">ONEZAE HEALTH CLINIC</h2>
              <p className="rx-hospital-sub">Comprehensive Outpatient & Specialty Care</p>
              <p className="rx-hospital-contact">Emergency: 112 · Helpline: +91 44 2800 1234 · www.onezae.health</p>
            </div>
          </div>
          <div className="rx-serial-badge">
            <span className="rx-serial-label">PRESCRIPTION NO.</span>
            <span className="rx-serial-number">RX-{prescription.id.toString().padStart(6, '0')}</span>
          </div>
        </div>

        <div className="rx-divider" />

        {/* Doctor & Patient Info Grid */}
        <div className="rx-meta-grid">
          <div className="rx-meta-box">
            <span className="rx-meta-label">PRESCRIBING DOCTOR</span>
            <div className="rx-doctor-name">Dr. {prescription.doctor.full_name}</div>
            <div className="rx-meta-detail">
              {prescription.doctor.qualification || 'MBBS, MD'}
            </div>
            <div className="rx-meta-detail muted">
              {prescription.doctor.specializations.length > 0
                ? prescription.doctor.specializations.join(' · ')
                : 'General Medicine'}
            </div>
          </div>

          <div className="rx-meta-box">
            <span className="rx-meta-label">PATIENT DETAILS</span>
            <div className="rx-patient-name">{prescription.patient.full_name}</div>
            <div className="rx-meta-detail">
              {prescription.patient.gender ? `${prescription.patient.gender} · ` : ''}
              {prescription.patient.date_of_birth ? `DOB: ${prescription.patient.date_of_birth}` : ''}
              {!prescription.patient.gender && !prescription.patient.date_of_birth && 'Registered Patient'}
            </div>
            <div className="rx-meta-detail muted">
              {prescription.patient.phone ? `Phone: ${prescription.patient.phone}` : prescription.patient.email}
            </div>
          </div>
        </div>

        <div className="rx-date-bar">
          <div>
            <strong>Date:</strong> {formatDate(prescription.created_at, timeZone)}
          </div>
          {prescription.appointment_id && (
            <div>
              <strong>Appointment:</strong> #{prescription.appointment_id}
            </div>
          )}
          {prescription.follow_up_date && (
            <div className="rx-follow-badge">
              <strong>Follow-up:</strong> {prescription.follow_up_date}
            </div>
          )}
        </div>

        {/* Diagnosis */}
        <div className="rx-diagnosis-section">
          <span className="rx-symbol">℞</span>
          <div className="rx-diagnosis-text">
            <strong>Diagnosis / Clinical Condition:</strong>
            <span className="rx-diagnosis-value">{prescription.diagnosis}</span>
          </div>
        </div>

        {/* Medications Table */}
        <div className="rx-table-wrap">
          <table className="rx-table">
            <thead>
              <tr>
                <th style={{ width: '40px' }}>#</th>
                <th>Medicine & Strength</th>
                <th>Dosage</th>
                <th>Frequency</th>
                <th>Timing</th>
                <th>Duration</th>
                <th>Instructions</th>
              </tr>
            </thead>
            <tbody>
              {prescription.items.map((item, idx) => (
                <tr key={item.id || idx}>
                  <td className="center-text">{idx + 1}</td>
                  <td>
                    <strong>{item.medicine_name}</strong>
                  </td>
                  <td>{item.dosage}</td>
                  <td>
                    <span className="rx-pill-badge">{item.frequency}</span>
                  </td>
                  <td>{item.timing}</td>
                  <td>{item.duration_days} days</td>
                  <td className="muted small-text">{item.instructions || '–'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Clinical Advice & Lifestyle Guidelines */}
        {(prescription.advice || prescription.notes) && (
          <div className="rx-advice-section">
            {prescription.advice && (
              <div className="rx-advice-block">
                <h4>Dietary & Lifestyle Advice:</h4>
                <p>{prescription.advice}</p>
              </div>
            )}
            {prescription.notes && (
              <div className="rx-advice-block">
                <h4>Doctor&apos;s Notes:</h4>
                <p>{prescription.notes}</p>
              </div>
            )}
          </div>
        )}

        {/* Prescription Footer & Signature */}
        <div className="rx-footer">
          <div className="rx-footer-note">
            <p className="small-text muted">
              This digital prescription is electronically verified and compliant with clinical care standards.
              In case of adverse drug reactions, discontinue immediately and contact emergency care.
            </p>
          </div>
          <div className="rx-signature-block">
            <div className="rx-signature-line" />
            <div className="rx-signature-name">Dr. {prescription.doctor.full_name}</div>
            <div className="small-text muted">Authorized Medical Practitioner</div>
          </div>
        </div>
      </div>
    </Modal>
  );
}
