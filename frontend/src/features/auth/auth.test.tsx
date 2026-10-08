import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import RegisterPage from '@/pages/RegisterPage';
import { apiError, makeAuth, makeUser, renderRoutes } from '@/test/utils';

import { GuestRoute, RoleRoute } from './guards';
import { LoginForm } from './LoginForm';

const marker = (text: string) => <p>{text}</p>;

function guardedRoutes() {
  return [
    {
      path: '/patient',
      element: <RoleRoute roles={['PATIENT']} />,
      children: [{ index: true, element: marker('patient area') }],
    },
    {
      path: '/admin',
      element: <RoleRoute roles={['ADMIN']} />,
      children: [{ index: true, element: marker('admin area') }],
    },
    {
      path: '/doctor',
      element: <RoleRoute roles={['DOCTOR']} />,
      children: [{ index: true, element: marker('doctor area') }],
    },
    { path: '/login', element: marker('patient login') },
    { path: '/staff/login', element: marker('staff login') },
    { path: '/change-password', element: marker('change password') },
  ];
}

describe('RoleRoute', () => {
  it('sends anonymous users to the matching login page', async () => {
    renderRoutes(guardedRoutes(), { initialPath: '/patient' });
    expect(await screen.findByText('patient login')).toBeInTheDocument();
  });

  it('sends anonymous staff-area visitors to the staff login', async () => {
    renderRoutes(guardedRoutes(), { initialPath: '/admin' });
    expect(await screen.findByText('staff login')).toBeInTheDocument();
  });

  it('redirects a patient away from the admin area to their own home', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    renderRoutes(guardedRoutes(), { initialPath: '/admin', auth });
    expect(await screen.findByText('patient area')).toBeInTheDocument();
  });

  it('redirects a doctor away from the admin area', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('DOCTOR') });
    renderRoutes(guardedRoutes(), { initialPath: '/admin', auth });
    expect(await screen.findByText('doctor area')).toBeInTheDocument();
  });

  it('forces a temporary password to be changed first', async () => {
    const auth = makeAuth({
      status: 'authenticated',
      user: makeUser('DOCTOR', { must_change_password: true }),
    });
    renderRoutes(guardedRoutes(), { initialPath: '/doctor', auth });
    expect(await screen.findByText('change password')).toBeInTheDocument();
  });

  it('renders the area for the right role', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('ADMIN') });
    renderRoutes(guardedRoutes(), { initialPath: '/admin', auth });
    expect(await screen.findByText('admin area')).toBeInTheDocument();
  });
});

function loginRoutes(portal: 'patient' | 'staff') {
  return [
    {
      element: <GuestRoute />,
      children: [
        {
          path: '/login',
          element: <LoginForm portal={portal} title="Sign in" subtitle="" footer={null} />,
        },
      ],
    },
    { path: '/patient', element: marker('patient home') },
    { path: '/admin', element: marker('admin home') },
    { path: '/change-password', element: marker('change password') },
  ];
}

async function fillLogin() {
  await userEvent.type(screen.getByLabelText('Email'), 'user@example.com');
  await userEvent.type(screen.getByLabelText('Password'), 'Passw0rd!');
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

describe('LoginForm', () => {
  it('logs a patient in through the patient portal', async () => {
    const login = vi.fn().mockResolvedValue(makeUser('PATIENT'));
    renderRoutes(loginRoutes('patient'), { initialPath: '/login', auth: makeAuth({ login }) });
    await fillLogin();
    expect(login).toHaveBeenCalledWith({
      email: 'user@example.com',
      password: 'Passw0rd!',
      portal: 'patient',
    });
    expect(await screen.findByText('patient home')).toBeInTheDocument();
  });

  it('uses the staff portal and routes admins to the admin area', async () => {
    const login = vi.fn().mockResolvedValue(makeUser('ADMIN'));
    renderRoutes(loginRoutes('staff'), { initialPath: '/login', auth: makeAuth({ login }) });
    await fillLogin();
    expect(login.mock.calls[0]?.[0].portal).toBe('staff');
    expect(await screen.findByText('admin home')).toBeInTheDocument();
  });

  it('sends doctors with a temporary password to change it', async () => {
    const login = vi.fn().mockResolvedValue(makeUser('DOCTOR', { must_change_password: true }));
    renderRoutes(loginRoutes('staff'), { initialPath: '/login', auth: makeAuth({ login }) });
    await fillLogin();
    expect(await screen.findByText('change password')).toBeInTheDocument();
  });

  it('validates before calling the API', async () => {
    const login = vi.fn();
    renderRoutes(loginRoutes('patient'), { initialPath: '/login', auth: makeAuth({ login }) });
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    expect(screen.getByText('Email is required')).toBeInTheDocument();
    expect(screen.getByText('Password is required')).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it('shows the API error message', async () => {
    const login = vi
      .fn()
      .mockRejectedValue(apiError(401, 'invalid_credentials', 'Invalid email or password'));
    renderRoutes(loginRoutes('patient'), { initialPath: '/login', auth: makeAuth({ login }) });
    await fillLogin();
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email or password');
  });
});

describe('RegisterPage', () => {
  const routes = [
    { path: '/register', element: <RegisterPage /> },
    { path: '/patient', element: marker('patient home') },
  ];

  it('validates the form', async () => {
    const register = vi.fn();
    renderRoutes(routes, { initialPath: '/register', auth: makeAuth({ register }) });
    await userEvent.type(screen.getByLabelText('Email'), 'not-an-email');
    await userEvent.type(screen.getByLabelText('Password'), 'lettersonly');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'different1');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(screen.getByText('First name is required')).toBeInTheDocument();
    expect(screen.getByText('Enter a valid email address')).toBeInTheDocument();
    expect(screen.getByText('Include at least one letter and one number')).toBeInTheDocument();
    expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });

  it('registers a patient', async () => {
    const register = vi.fn().mockResolvedValue(makeUser('PATIENT'));
    renderRoutes(routes, { initialPath: '/register', auth: makeAuth({ register }) });
    await userEvent.type(screen.getByLabelText('First name'), 'Priya');
    await userEvent.type(screen.getByLabelText('Email'), 'priya@example.com');
    await userEvent.type(screen.getByLabelText('Password'), 'Secur3pass');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'Secur3pass');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));

    expect(register).toHaveBeenCalledWith({
      first_name: 'Priya',
      last_name: undefined,
      email: 'priya@example.com',
      password: 'Secur3pass',
    });
    expect(await screen.findByText('patient home')).toBeInTheDocument();
  });
});
