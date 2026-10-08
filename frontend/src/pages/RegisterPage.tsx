import { type FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { AuthLayout } from '@/components/AuthLayout';
import { FormField } from '@/components/FormField';
import { Alert } from '@/components/ui';
import { useAuth } from '@/features/auth/useAuth';
import { getErrorMessage } from '@/lib/errors';
import {
  type Errors,
  hasErrors,
  validateEmail,
  validatePassword,
  validateRequired,
} from '@/lib/validation';

type Field = 'first_name' | 'email' | 'password' | 'confirm';

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [values, setValues] = useState({
    first_name: '',
    last_name: '',
    email: '',
    password: '',
    confirm: '',
  });
  const [errors, setErrors] = useState<Errors<Field>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const set = (field: keyof typeof values) => (event: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [field]: event.target.value }));

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors: Errors<Field> = {
      first_name: validateRequired(values.first_name, 'First name'),
      email: validateEmail(values.email),
      password: validatePassword(values.password),
      confirm: values.password === values.confirm ? undefined : 'Passwords do not match',
    };
    setErrors(nextErrors);
    if (hasErrors(nextErrors)) return;

    setError(null);
    setSubmitting(true);
    try {
      await register({
        first_name: values.first_name.trim(),
        last_name: values.last_name.trim() || undefined,
        email: values.email.trim(),
        password: values.password,
      });
      void navigate('/patient', { replace: true });
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout>
      <form className="card stack" onSubmit={handleSubmit} noValidate>
        <div>
          <h1>Create your patient account</h1>
          <p className="muted">It takes less than a minute.</p>
        </div>
        {error && <Alert>{error}</Alert>}
        <div className="grid-2">
          <FormField
            label="First name"
            autoComplete="given-name"
            value={values.first_name}
            error={errors.first_name}
            maxLength={100}
            onChange={set('first_name')}
          />
          <FormField
            label="Last name (optional)"
            autoComplete="family-name"
            value={values.last_name}
            maxLength={100}
            onChange={set('last_name')}
          />
        </div>
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          value={values.email}
          error={errors.email}
          onChange={set('email')}
        />
        <FormField
          label="Password"
          type="password"
          autoComplete="new-password"
          hint="At least 8 characters with a letter and a number."
          value={values.password}
          error={errors.password}
          onChange={set('password')}
        />
        <FormField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          value={values.confirm}
          error={errors.confirm}
          onChange={set('confirm')}
        />
        <button type="submit" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </button>
        <p className="muted small-text">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
