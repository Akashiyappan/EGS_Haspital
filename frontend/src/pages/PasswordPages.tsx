import { type FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { AuthLayout } from '@/components/AuthLayout';
import { FormField } from '@/components/FormField';
import { Alert } from '@/components/ui';
import { authApi } from '@/features/auth/api';
import { HOME_BY_ROLE } from '@/features/auth/roles';
import { useAuth } from '@/features/auth/useAuth';
import { getErrorMessage } from '@/lib/errors';
import { validateEmail, validatePassword } from '@/lib/validation';

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [fieldError, setFieldError] = useState<string>();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const invalid = validateEmail(email);
    setFieldError(invalid);
    if (invalid) return;
    setSubmitting(true);
    setError(null);
    try {
      setMessage((await authApi.forgotPassword(email.trim())).message);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <form className="card stack" onSubmit={submit} noValidate>
        <div>
          <h1>Reset your password</h1>
          <p className="muted">We'll email you a link to choose a new password.</p>
        </div>
        {message && <Alert tone="success">{message}</Alert>}
        {error && <Alert>{error}</Alert>}
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          error={fieldError}
          onChange={(event) => setEmail(event.target.value)}
        />
        <button type="submit" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send reset link'}
        </button>
        <Link to="/login" className="small-text">
          Back to sign in
        </Link>
      </form>
    </AuthLayout>
  );
}

export function ResetPasswordPage() {
  // The token travels in the URL fragment so it is never sent to servers or logged.
  const token = new URLSearchParams(window.location.hash.slice(1)).get('token') ?? '';
  const [password, setPassword] = useState('');
  const [fieldError, setFieldError] = useState<string>();
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const invalid = validatePassword(password);
    setFieldError(invalid);
    if (invalid) return;
    setSubmitting(true);
    setError(null);
    try {
      await authApi.resetPassword(token, password);
      setDone(true);
      window.history.replaceState(null, '', window.location.pathname);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <form className="card stack" onSubmit={submit} noValidate>
        <h1>Choose a new password</h1>
        {!token && <Alert>This reset link is incomplete. Please request a new one.</Alert>}
        {done ? (
          <>
            <Alert tone="success">Your password has been reset.</Alert>
            <Link to="/login" className="button">
              Sign in
            </Link>
          </>
        ) : (
          <>
            {error && <Alert>{error}</Alert>}
            <FormField
              label="New password"
              type="password"
              autoComplete="new-password"
              hint="At least 8 characters with a letter and a number."
              value={password}
              error={fieldError}
              onChange={(event) => setPassword(event.target.value)}
            />
            <button type="submit" disabled={submitting || !token}>
              {submitting ? 'Saving…' : 'Set new password'}
            </button>
          </>
        )}
      </form>
    </AuthLayout>
  );
}

export function ChangePasswordPage() {
  const { user, changePassword, logout } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState<{ next?: string; confirm?: string }>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const forced = user?.must_change_password ?? false;

  async function submit(event: FormEvent) {
    event.preventDefault();
    const nextErrors = {
      next: validatePassword(next),
      confirm: next === confirm ? undefined : 'Passwords do not match',
    };
    setErrors(nextErrors);
    if (nextErrors.next || nextErrors.confirm) return;
    setSubmitting(true);
    setError(null);
    try {
      const me = await changePassword({ current_password: current, new_password: next });
      void navigate(HOME_BY_ROLE[me.role], { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout variant={user?.role === 'PATIENT' ? 'patient' : 'staff'}>
      <form className="card stack" onSubmit={submit} noValidate>
        <div>
          <h1>{forced ? 'Set your password' : 'Change password'}</h1>
          {forced && (
            <p className="muted">
              Your account was created with a temporary password. Choose a new one to continue.
            </p>
          )}
        </div>
        {error && <Alert>{error}</Alert>}
        <FormField
          label={forced ? 'Temporary password' : 'Current password'}
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <FormField
          label="New password"
          type="password"
          autoComplete="new-password"
          hint="At least 8 characters with a letter and a number."
          value={next}
          error={errors.next}
          onChange={(event) => setNext(event.target.value)}
        />
        <FormField
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          error={errors.confirm}
          onChange={(event) => setConfirm(event.target.value)}
        />
        <button type="submit" disabled={submitting || !current}>
          {submitting ? 'Saving…' : 'Save password'}
        </button>
        {forced ? (
          <button type="button" className="secondary" onClick={() => void logout()}>
            Sign out
          </button>
        ) : (
          user && (
            <Link to={HOME_BY_ROLE[user.role]} className="small-text">
              Cancel
            </Link>
          )
        )}
      </form>
    </AuthLayout>
  );
}
