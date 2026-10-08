import { type FormEvent, type ReactNode, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';

import { FormField } from '@/components/FormField';
import { Alert } from '@/components/ui';
import { getErrorMessage } from '@/lib/errors';
import { type Errors, hasErrors, validateEmail } from '@/lib/validation';

import { HOME_BY_ROLE } from './roles';
import type { Portal } from './types';
import { useAuth } from './useAuth';

export function LoginForm({
  portal,
  title,
  subtitle,
  footer,
}: {
  portal: Portal;
  title: string;
  subtitle: string;
  footer: ReactNode;
}) {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<Errors<'email' | 'password'>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = {
      email: validateEmail(email),
      password: password ? undefined : 'Password is required',
    };
    setErrors(nextErrors);
    if (hasErrors(nextErrors)) return;

    setError(null);
    setSubmitting(true);
    try {
      const me = await login({ email, password, portal });
      if (me.must_change_password) {
        void navigate('/change-password', { replace: true });
      } else {
        const home = HOME_BY_ROLE[me.role];
        void navigate(from?.startsWith(home) ? from : home, { replace: true });
      }
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card stack" onSubmit={handleSubmit} noValidate>
      <div>
        <h1>{title}</h1>
        <p className="muted">{subtitle}</p>
      </div>
      {error && <Alert>{error}</Alert>}
      <FormField
        label="Email"
        name="email"
        type="email"
        autoComplete="email"
        value={email}
        error={errors.email}
        onChange={(event) => setEmail(event.target.value)}
      />
      <FormField
        label="Password"
        name="password"
        type="password"
        autoComplete="current-password"
        value={password}
        error={errors.password}
        onChange={(event) => setPassword(event.target.value)}
      />
      <button type="submit" disabled={submitting}>
        {submitting ? 'Signing in…' : 'Sign in'}
      </button>
      {footer}
    </form>
  );
}
