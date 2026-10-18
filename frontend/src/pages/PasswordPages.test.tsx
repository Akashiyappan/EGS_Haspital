import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { authApi } from '@/features/auth/api';
import { makeAuth, makeUser, renderRoutes } from '@/test/utils';

import { ChangePasswordPage, ForgotPasswordPage, ResetPasswordPage } from './PasswordPages';

vi.mock('@/features/auth/api', () => ({
  authApi: {
    forgotPassword: vi.fn(),
    resetPassword: vi.fn(),
  },
}));

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('validates email input', async () => {
    renderRoutes([{ path: '/forgot-password', element: <ForgotPasswordPage /> }], {
      initialPath: '/forgot-password',
    });

    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByText('Email is required')).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText('Email'), 'notanemail');
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }));
    expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument();
    expect(authApi.forgotPassword).not.toHaveBeenCalled();
  });

  it('submits valid email and displays confirmation message', async () => {
    vi.mocked(authApi.forgotPassword).mockResolvedValue({
      message: 'If this email is registered, a password reset link has been sent.',
    });

    renderRoutes([{ path: '/forgot-password', element: <ForgotPasswordPage /> }], {
      initialPath: '/forgot-password',
    });

    await userEvent.type(screen.getByLabelText('Email'), 'patient@example.com');
    await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }));

    expect(authApi.forgotPassword).toHaveBeenCalledWith('patient@example.com');
    expect(
      await screen.findByText(/If this email is registered, a password reset link has been sent./),
    ).toBeInTheDocument();
  });
});

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.location.hash = '';
  });

  it('shows error when token is missing from url hash', () => {
    renderRoutes([{ path: '/reset-password', element: <ResetPasswordPage /> }], {
      initialPath: '/reset-password',
    });

    expect(screen.getByText(/This reset link is incomplete/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set new password' })).toBeDisabled();
  });

  it('submits new password when token is present', async () => {
    window.location.hash = '#token=valid-jwt-token';
    vi.mocked(authApi.resetPassword).mockResolvedValue({ message: 'Password updated' });

    renderRoutes([{ path: '/reset-password', element: <ResetPasswordPage /> }], {
      initialPath: '/reset-password',
    });

    await userEvent.type(screen.getByLabelText('New password'), 'NewSecurePass1');
    await userEvent.click(screen.getByRole('button', { name: 'Set new password' }));

    expect(authApi.resetPassword).toHaveBeenCalledWith('valid-jwt-token', 'NewSecurePass1');
    expect(await screen.findByText('Your password has been reset.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Sign in' })).toBeInTheDocument();
  });
});

describe('ChangePasswordPage', () => {
  it('validates password match and strength', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR', { must_change_password: true }),
    });

    renderRoutes([{ path: '/change-password', element: <ChangePasswordPage /> }], {
      initialPath: '/change-password',
      auth,
    });

    await userEvent.type(screen.getByLabelText('Temporary password'), 'CurrentPass1');
    await userEvent.type(screen.getByLabelText('New password'), 'weak');
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'mismatch');
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }));

    expect(screen.getByText('Use at least 8 characters')).toBeInTheDocument();
    expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
  });

  it('submits valid password change and redirects to home', async () => {
    const changePassword = vi.fn().mockResolvedValue(makeUser('DOCTOR'));
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR', { must_change_password: true }),
      changePassword,
    });

    renderRoutes(
      [
        { path: '/change-password', element: <ChangePasswordPage /> },
        { path: '/doctor', element: <p>doctor home</p> },
      ],
      { initialPath: '/change-password', auth },
    );

    await userEvent.type(screen.getByLabelText('Temporary password'), 'CurrentPass1');
    await userEvent.type(screen.getByLabelText('New password'), 'NewBrandPass1');
    await userEvent.type(screen.getByLabelText('Confirm new password'), 'NewBrandPass1');
    await userEvent.click(screen.getByRole('button', { name: 'Save password' }));

    expect(changePassword).toHaveBeenCalledWith({
      current_password: 'CurrentPass1',
      new_password: 'NewBrandPass1',
    });
    expect(await screen.findByText('doctor home')).toBeInTheDocument();
  });
});
