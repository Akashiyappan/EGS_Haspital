import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeAuth, makeUser, renderRoutes } from '@/test/utils';

import {
  AdminAuditPage,
  AdminDashboard,
  AdminDoctorsPage,
  AdminSpecializationsPage,
  AdminUsersPage,
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

const mockStats = {
  doctors_active: 5,
  doctors_inactive: 1,
  patients: 20,
  appointments_today: 4,
  appointments_upcoming: 12,
  appointments_by_status: { BOOKED: 8, CONFIRMED: 4 },
};

const mockDoctorAdmin = {
  id: 10,
  user_id: 10,
  first_name: 'Suresh',
  last_name: 'Raina',
  full_name: 'Suresh Raina',
  email: 'suresh@example.com',
  phone: '+91 98765 22222',
  avatar_url: null,
  qualification: 'MS, MCh',
  experience_years: 15,
  bio: 'Senior Neurologist',
  is_active: true,
  must_change_password: false,
  specializations: [{ id: 2, name: 'Neurology', description: null, is_active: true }],
};

const mockUserRow = {
  id: 15,
  first_name: 'Amit',
  last_name: 'Kumar',
  full_name: 'Amit Kumar',
  email: 'amit@example.com',
  phone: '+91 99999 88888',
  avatar_url: null,
  role: 'PATIENT',
  is_active: true,
  must_change_password: false,
  created_at: '2030-01-01T00:00:00Z',
};

const mockAuditLog = {
  id: 1,
  action: 'doctor.created',
  actor_id: 1,
  actor_name: 'Admin User',
  entity_type: 'doctor',
  entity_id: '10',
  ip_address: '127.0.0.1',
  user_agent: 'Browser',
  details: { name: 'Suresh Raina' },
  created_at: '2030-05-01T10:00:00Z',
};

describe('AdminPortalPages', () => {
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
      if (url === '/admin/stats') {
        return Promise.resolve({ data: mockStats });
      }
      if (url.startsWith('/admin/doctors')) {
        return Promise.resolve({
          data: { items: [mockDoctorAdmin], total: 1, page: 1, page_size: 10, pages: 1 },
        });
      }
      if (url.startsWith('/admin/specializations') || url === '/specializations') {
        return Promise.resolve({
          data: [{ id: 2, name: 'Neurology', description: 'Brain and nerves', is_active: true }],
        });
      }
      if (url.startsWith('/admin/users')) {
        return Promise.resolve({
          data: { items: [mockUserRow], total: 1, page: 1, page_size: 10, pages: 1 },
        });
      }
      if (url.startsWith('/admin/audit-logs')) {
        return Promise.resolve({
          data: { items: [mockAuditLog], total: 1, page: 1, page_size: 50, pages: 1 },
        });
      }
      if (url.startsWith('/appointments')) {
        return Promise.resolve({
          data: { items: [], total: 0, page: 1, page_size: 10, pages: 0 },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('renders AdminDashboard with stats cards', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('ADMIN', { first_name: 'Admin' }),
    });

    renderRoutes([{ path: '/admin', element: <AdminDashboard /> }], {
      initialPath: '/admin',
      auth,
    });

    expect(await screen.findByText('Administration')).toBeInTheDocument();
    expect(await screen.findByText('Active doctors')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('Patients')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
  });

  it('renders AdminDoctorsPage with doctor table', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('ADMIN'),
    });

    renderRoutes([{ path: '/admin/doctors', element: <AdminDoctorsPage /> }], {
      initialPath: '/admin/doctors',
      auth,
    });

    expect(await screen.findByText(/Suresh Raina/)).toBeInTheDocument();
    expect(screen.getByText('suresh@example.com')).toBeInTheDocument();
    expect(screen.getAllByText('Neurology').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Active').length).toBeGreaterThan(0);
  });

  it('renders AdminSpecializationsPage with specializations list', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('ADMIN'),
    });

    renderRoutes([{ path: '/admin/specializations', element: <AdminSpecializationsPage /> }], {
      initialPath: '/admin/specializations',
      auth,
    });

    expect(await screen.findByText('Specializations')).toBeInTheDocument();
    expect(await screen.findByText('Neurology')).toBeInTheDocument();
    expect(screen.getByText('Brain and nerves')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument();
  });

  it('renders AdminUsersPage and displays user accounts', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('ADMIN'),
    });

    renderRoutes([{ path: '/admin/users', element: <AdminUsersPage /> }], {
      initialPath: '/admin/users',
      auth,
    });

    expect(await screen.findByText('Users')).toBeInTheDocument();
    expect(await screen.findByText('Amit Kumar')).toBeInTheDocument();
    expect(screen.getByText('amit@example.com')).toBeInTheDocument();
    expect(screen.getByText('patient')).toBeInTheDocument();
  });

  it('renders AdminAuditPage and displays activity logs', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('ADMIN'),
    });

    renderRoutes([{ path: '/admin/audit', element: <AdminAuditPage /> }], {
      initialPath: '/admin/audit',
      auth,
    });

    expect(await screen.findByText('Audit log')).toBeInTheDocument();
    expect(await screen.findByText('Added doctor')).toBeInTheDocument();
    expect(screen.getByText('Doctor #10')).toBeInTheDocument();
  });
});
