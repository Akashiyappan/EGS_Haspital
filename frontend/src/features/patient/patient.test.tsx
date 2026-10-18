import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeAuth, makeUser, renderRoutes } from '@/test/utils';

import {
  DoctorProfilePage,
  FindDoctorsPage,
  PatientAppointmentsPage,
  PatientDashboard,
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

const mockDoctor = {
  id: 1,
  first_name: 'Anjali',
  last_name: 'Menon',
  full_name: 'Anjali Menon',
  avatar_url: null,
  qualification: 'MBBS, MD',
  experience_years: 10,
  bio: 'Experienced cardiologist.',
  specializations: [{ id: 1, name: 'Cardiology', description: null, is_active: true }],
};

const mockAppointment = {
  id: 101,
  starts_at: '2030-05-10T10:00:00Z',
  ends_at: '2030-05-10T10:30:00Z',
  status: 'BOOKED',
  reason: 'Heart checkup',
  doctor_notes: null,
  cancellation_reason: null,
  cancelled_at: null,
  created_at: '2030-05-01T00:00:00Z',
  doctor: { id: 1, full_name: 'Dr. Anjali Menon', avatar_url: null, specializations: ['Cardiology'] },
  patient: { id: 2, full_name: 'Priya Sharma', avatar_url: null },
  allowed_actions: ['cancel'],
};

describe('PatientPortalPages', () => {
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
        return Promise.resolve({ data: { unread: 2 } });
      }
      if (url.startsWith('/appointments')) {
        return Promise.resolve({
          data: { items: [mockAppointment], total: 1, page: 1, page_size: 10, pages: 1 },
        });
      }
      if (url === '/specializations') {
        return Promise.resolve({
          data: [{ id: 1, name: 'Cardiology', description: null, is_active: true }],
        });
      }
      if (url.startsWith('/doctors/1/availability')) {
        return Promise.resolve({
          data: {
            doctor_id: 1,
            timezone: 'Asia/Kolkata',
            days: [{ date: '2030-05-10', available_slots: 3 }],
          },
        });
      }
      if (url.startsWith('/doctors/1/slots')) {
        return Promise.resolve({
          data: {
            doctor_id: 1,
            date: '2030-05-10',
            timezone: 'Asia/Kolkata',
            slots: [
              {
                starts_at: '2030-05-10T10:00:00Z',
                ends_at: '2030-05-10T10:30:00Z',
                available: true,
              },
            ],
          },
        });
      }
      if (url === '/doctors/1') {
        return Promise.resolve({ data: mockDoctor });
      }
      if (url.startsWith('/doctors')) {
        return Promise.resolve({
          data: { items: [mockDoctor], total: 1, page: 1, page_size: 10, pages: 1 },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('renders PatientDashboard with next appointment and stats', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('PATIENT', { first_name: 'Priya' }),
    });

    renderRoutes([{ path: '/patient', element: <PatientDashboard /> }], {
      initialPath: '/patient',
      auth,
    });

    expect(await screen.findByText(/Hello, Priya/)).toBeInTheDocument();
    expect(await screen.findByText('Next appointment')).toBeInTheDocument();
    expect(screen.getByText('Upcoming')).toBeInTheDocument();
    expect(screen.getByText('Unread messages')).toBeInTheDocument();
    expect(await screen.findByText(/Anjali Menon/)).toBeInTheDocument();
  });

  it('renders FindDoctorsPage and lists doctors', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('PATIENT'),
    });

    renderRoutes([{ path: '/patient/doctors', element: <FindDoctorsPage /> }], {
      initialPath: '/patient/doctors',
      auth,
    });

    expect(await screen.findByText(/Anjali Menon/)).toBeInTheDocument();
    expect(screen.getAllByText('Cardiology').length).toBeGreaterThan(0);
    expect(screen.getByPlaceholderText('Search doctors or specializations')).toBeInTheDocument();
  });

  it('renders DoctorProfilePage with doctor info and booking options', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('PATIENT'),
    });

    renderRoutes([{ path: '/patient/doctors/:doctorId', element: <DoctorProfilePage /> }], {
      initialPath: '/patient/doctors/1',
      auth,
    });

    expect(await screen.findByText(/Anjali Menon/)).toBeInTheDocument();
    expect(screen.getByText('Experienced cardiologist.')).toBeInTheDocument();
    expect(screen.getByText('Book an appointment')).toBeInTheDocument();
  });

  it('renders PatientAppointmentsPage with tabs', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('PATIENT'),
    });

    renderRoutes([{ path: '/patient/appointments', element: <PatientAppointmentsPage /> }], {
      initialPath: '/patient/appointments',
      auth,
    });

    expect(await screen.findByText('Upcoming')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(await screen.findByText(/Anjali Menon/)).toBeInTheDocument();
    expect(screen.getByText('Booked')).toBeInTheDocument();
  });
});
