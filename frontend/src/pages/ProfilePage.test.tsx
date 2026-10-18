import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeAuth, makeUser, renderPage } from '@/test/utils';

import ProfilePage from './ProfilePage';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api,
  tokenStore: { get: () => 'token', set: vi.fn() },
  refreshAccessToken: vi.fn().mockResolvedValue('token'),
  setUnauthorizedHandler: vi.fn(),
}));

describe('ProfilePage', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.get.mockImplementation((url: string) => {
      if (url === '/meta') {
        return Promise.resolve({
          data: {
            app_name: 'Onezae Health',
            clinic_timezone: 'Asia/Kolkata',
            upload_max_bytes: 5242880,
            upload_allowed_types: ['image/jpeg', 'image/png', 'image/webp'],
            uploads_enabled: true,
          },
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('renders patient profile with patient specific fields', async () => {
    const patientUser = makeUser('PATIENT', {
      first_name: 'Priya',
      last_name: 'Sharma',
      phone: '+91 98765 43210',
      patient: {
        id: 1,
        date_of_birth: '1990-01-01',
        gender: 'female',
        emergency_contact_name: 'Aarav Sharma',
        emergency_contact_phone: '+91 98765 00000',
      },
    });
    const auth = makeAuth({ status: 'authenticated', user: patientUser });

    renderPage(<ProfilePage />, { auth });

    expect(screen.getByLabelText('First name')).toHaveValue('Priya');
    expect(screen.getByLabelText('Last name')).toHaveValue('Sharma');
    expect(screen.getByLabelText('Email')).toHaveValue(patientUser.email);
    expect(screen.getByLabelText('Date of birth')).toHaveValue('1990-01-01');
    expect(screen.getByLabelText('Gender')).toHaveValue('female');
    expect(screen.getByLabelText('Emergency contact name')).toHaveValue('Aarav Sharma');
  });

  it('updates patient profile details successfully', async () => {
    const patientUser = makeUser('PATIENT', { first_name: 'Priya', last_name: '' });
    const auth = makeAuth({ status: 'authenticated', user: patientUser });
    api.patch.mockResolvedValue({
      data: {
        ...patientUser,
        first_name: 'Priyanka',
        last_name: 'Kapoor',
      },
    });

    renderPage(<ProfilePage />, { auth });

    const firstNameInput = screen.getByLabelText('First name');
    await userEvent.clear(firstNameInput);
    await userEvent.type(firstNameInput, 'Priyanka');

    const lastNameInput = screen.getByLabelText('Last name');
    await userEvent.clear(lastNameInput);
    await userEvent.type(lastNameInput, 'Kapoor');

    await userEvent.click(screen.getByRole('button', { name: 'Save changes' }));

    await waitFor(() => {
      expect(api.patch).toHaveBeenCalledWith(
        '/users/me',
        expect.objectContaining({
          first_name: 'Priyanka',
          last_name: 'Kapoor',
        }),
      );
    });
    expect(await screen.findByText('Profile saved.')).toBeInTheDocument();
  });

  it('hides patient fields for doctor profile', () => {
    const doctorUser = makeUser('DOCTOR', { first_name: 'Dr. Vikram' });
    const auth = makeAuth({ status: 'authenticated', user: doctorUser });

    renderPage(<ProfilePage />, { auth });

    expect(screen.getByLabelText('First name')).toHaveValue('Dr. Vikram');
    expect(screen.queryByLabelText('Date of birth')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Emergency contact name')).not.toBeInTheDocument();
  });
});
