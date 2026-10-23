import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { Prescription } from '@/lib/types';
import { makeAuth, makeUser, renderRoutes } from '@/test/utils';

import { DoctorPrescriptionsPage } from './DoctorPrescriptionsPage';
import { PatientPrescriptionsPage } from './PatientPrescriptionsPage';
import { PrescriptionPrintModal } from './PrescriptionPrintModal';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api,
  tokenStore: { get: () => 'token', set: vi.fn() },
  refreshAccessToken: vi.fn().mockResolvedValue('token'),
  setUnauthorizedHandler: vi.fn(),
}));

const mockPrescription: Prescription = {
  id: 42,
  appointment_id: 101,
  doctor_id: 1,
  patient_id: 2,
  diagnosis: 'Acute Upper Respiratory Tract Infection',
  notes: 'Chest is clear on auscultation.',
  advice: 'Drink warm water and rest for 3 days.',
  follow_up_date: '2030-05-18',
  created_at: '2030-05-11T10:00:00Z',
  updated_at: '2030-05-11T10:00:00Z',
  doctor: {
    id: 1,
    user_id: 10,
    full_name: 'Anjali Menon',
    avatar_url: null,
    qualification: 'MBBS, MD',
    specializations: ['Cardiology'],
  },
  patient: {
    id: 2,
    user_id: 20,
    full_name: 'Priya Sharma',
    email: 'priya@example.com',
    phone: '+91 98765 43210',
    avatar_url: null,
    date_of_birth: '1995-04-12',
    gender: 'Female',
  },
  items: [
    {
      id: 1,
      medicine_name: 'Amoxicillin 500mg',
      dosage: '1 capsule',
      frequency: '1-1-1 (Thrice daily)',
      timing: 'After food',
      duration_days: 5,
      instructions: 'Complete full course',
    },
    {
      id: 2,
      medicine_name: 'Paracetamol 650mg',
      dosage: '1 tablet',
      frequency: 'SOS (As needed)',
      timing: 'After food',
      duration_days: 3,
      instructions: 'For fever or severe pain',
    },
  ],
  is_active: true,
  days_remaining: 4,
};

describe('Prescription Components & Pages', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.get.mockImplementation((url: string) => {
      if (url === '/meta') {
        return Promise.resolve({
          data: {
            app_name: 'Onezae Health',
            clinic_timezone: 'Asia/Kolkata',
            appointment_duration_minutes: 30,
            cancellation_cutoff_hours: 2,
            booking_window_days: 60,
            upload_max_bytes: 5242880,
            upload_allowed_types: ['image/jpeg', 'image/png'],
            uploads_enabled: true,
            ai_enabled: true,
          },
        });
      }
      if (url === '/prescriptions') {
        return Promise.resolve({ data: [mockPrescription] });
      }
      if (url === '/doctor/patients') {
        return Promise.resolve({
          data: {
            items: [
              {
                id: 2,
                first_name: 'Priya',
                last_name: 'Sharma',
                full_name: 'Priya Sharma',
                email: 'priya@example.com',
                phone: '+91 98765 43210',
                avatar_url: null,
                date_of_birth: '1995-04-12',
                gender: 'Female',
                appointment_count: 2,
                last_appointment_at: '2030-05-11T10:00:00Z',
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
            pages: 1,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('renders PrescriptionPrintModal with hospital letterhead and medications', () => {
    renderRoutes(
      [
        {
          path: '/',
          element: (
            <PrescriptionPrintModal
              open={true}
              prescription={mockPrescription}
              onClose={() => {}}
            />
          ),
        },
      ],
      { initialPath: '/' },
    );

    expect(screen.getByText('ONEZAE HEALTH CLINIC')).toBeInTheDocument();
    expect(screen.getByText('RX-000042')).toBeInTheDocument();
    expect(screen.getAllByText('Dr. Anjali Menon').length).toBe(2);
    expect(screen.getByText('Priya Sharma')).toBeInTheDocument();
    expect(screen.getByText('Acute Upper Respiratory Tract Infection')).toBeInTheDocument();
    expect(screen.getByText('Amoxicillin 500mg')).toBeInTheDocument();
    expect(screen.getByText('Paracetamol 650mg')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Print \/ Save as PDF/ })).toBeInTheDocument();
  });

  it('renders PatientPrescriptionsPage with active medication tracker and cards', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('PATIENT'),
    });

    renderRoutes([{ path: '/patient/prescriptions', element: <PatientPrescriptionsPage /> }], {
      initialPath: '/patient/prescriptions',
      auth,
    });

    expect(await screen.findByText('My Prescriptions & Medications')).toBeInTheDocument();
    expect(await screen.findByText("Today's Ongoing Medication Schedule")).toBeInTheDocument();
    expect(screen.getAllByText('Amoxicillin 500mg').length).toBeGreaterThan(0);
    expect(screen.getByText('Acute Upper Respiratory Tract Infection')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /View & Print Prescription/ })).toBeInTheDocument();
  });

  it('renders DoctorPrescriptionsPage with management table and new prescription button', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR'),
    });

    renderRoutes([{ path: '/doctor/prescriptions', element: <DoctorPrescriptionsPage /> }], {
      initialPath: '/doctor/prescriptions',
      auth,
    });

    expect(await screen.findByText('Prescriptions Management')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Issue New Prescription/ })).toBeInTheDocument();
    expect(await screen.findByText('Priya Sharma')).toBeInTheDocument();
    expect(screen.getByText('Acute Upper Respiratory Tract Infection')).toBeInTheDocument();
  });
});
