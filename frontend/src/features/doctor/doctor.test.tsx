import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeAuth, makeUser, renderRoutes } from '@/test/utils';

import {
  DoctorAppointmentsPage,
  DoctorDashboard,
  DoctorPatientDetailPage,
  DoctorPatientsPage,
  DoctorSchedulePage,
} from './pages';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api,
  tokenStore: { get: () => 'token', set: vi.fn() },
  refreshAccessToken: vi.fn().mockResolvedValue('token'),
  setUnauthorizedHandler: vi.fn(),
}));

const mockDoctorAppointment = {
  id: 201,
  starts_at: '2030-05-10T11:00:00Z',
  ends_at: '2030-05-10T11:30:00Z',
  status: 'CONFIRMED',
  reason: 'Routine check',
  doctor_notes: null,
  cancellation_reason: null,
  cancelled_at: null,
  created_at: '2030-05-01T00:00:00Z',
  doctor: { id: 1, full_name: 'Dr. Vikram Shah', avatar_url: null, specializations: ['Cardiology'] },
  patient: { id: 5, full_name: 'Rohan Mehra', avatar_url: null },
  allowed_actions: ['cancel', 'complete', 'no_show'],
};

const mockPatientRecord = {
  id: 5,
  first_name: 'Rohan',
  last_name: 'Mehra',
  full_name: 'Rohan Mehra',
  email: 'rohan@example.com',
  phone: '+91 98765 11111',
  avatar_url: null,
  date_of_birth: '1988-02-14',
  gender: 'male',
  last_appointment_at: '2030-05-10T11:00:00Z',
  appointment_count: 3,
};

describe('DoctorPortalPages', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.get.mockImplementation((url: string) => {
      if (url === '/meta') {
        return Promise.resolve({
          data: {
            app_name: 'Onezae Health',
            clinic_timezone: 'Asia/Kolkata',
            upload_max_bytes: 5242880,
            upload_allowed_types: ['image/jpeg', 'image/png'],
            uploads_enabled: true,
          },
        });
      }
      if (url === '/chat/unread-count') {
        return Promise.resolve({ data: { unread: 1 } });
      }
      if (url.startsWith('/doctor/patients/5')) {
        return Promise.resolve({ data: mockPatientRecord });
      }
      if (url.startsWith('/doctor/patients')) {
        return Promise.resolve({
          data: { items: [mockPatientRecord], total: 1, page: 1, page_size: 10, pages: 1 },
        });
      }
      if (url === '/doctor/schedule') {
        return Promise.resolve({
          data: {
            timezone: 'Asia/Kolkata',
            rules: [
              {
                id: 1,
                weekday: 0,
                start_time: '09:00',
                end_time: '17:00',
                slot_minutes: 30,
              },
            ],
            time_off: [],
          },
        });
      }
      if (url.startsWith('/appointments')) {
        return Promise.resolve({
          data: { items: [mockDoctorAppointment], total: 1, page: 1, page_size: 50, pages: 1 },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('renders DoctorDashboard with appointment counts and today appointments', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR', { first_name: 'Vikram', last_name: 'Shah' }),
    });

    renderRoutes([{ path: '/doctor', element: <DoctorDashboard /> }], {
      initialPath: '/doctor',
      auth,
    });

    expect(await screen.findByText(/Good day, Dr. Shah/)).toBeInTheDocument();
    expect(await screen.findByText("Today's appointments")).toBeInTheDocument();
    expect(screen.getByText('Unread messages')).toBeInTheDocument();
    expect(await screen.findByText(/Rohan Mehra/)).toBeInTheDocument();
    expect(screen.getByText(/Routine check/)).toBeInTheDocument();
  });

  it('renders DoctorAppointmentsPage with tabs', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR'),
    });

    renderRoutes([{ path: '/doctor/appointments', element: <DoctorAppointmentsPage /> }], {
      initialPath: '/doctor/appointments',
      auth,
    });

    expect(await screen.findByText('Today')).toBeInTheDocument();
    expect(screen.getByText('Upcoming')).toBeInTheDocument();
    expect(screen.getByText('Past')).toBeInTheDocument();
    expect(await screen.findByText(/Rohan Mehra/)).toBeInTheDocument();
  });

  it('renders DoctorPatientsPage with patient list and search', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR'),
    });

    renderRoutes([{ path: '/doctor/patients', element: <DoctorPatientsPage /> }], {
      initialPath: '/doctor/patients',
      auth,
    });

    expect(await screen.findByText('Rohan Mehra')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('Search by name')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument(); // visit count
  });

  it('renders DoctorPatientDetailPage with details and appointments', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR'),
    });

    renderRoutes([{ path: '/doctor/patients/:patientId', element: <DoctorPatientDetailPage /> }], {
      initialPath: '/doctor/patients/5',
      auth,
    });

    expect(await screen.findByText('rohan@example.com')).toBeInTheDocument();
    expect(screen.getByText('+91 98765 11111')).toBeInTheDocument();
    expect(await screen.findByText(/Routine check/)).toBeInTheDocument();
  });

  it('renders DoctorSchedulePage with working hours', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR'),
    });

    renderRoutes([{ path: '/doctor/schedule', element: <DoctorSchedulePage /> }], {
      initialPath: '/doctor/schedule',
      auth,
    });

    expect(await screen.findByText(/Monday/)).toBeInTheDocument();
    expect(screen.getByText(/09:00/)).toBeInTheDocument();
  });
});
