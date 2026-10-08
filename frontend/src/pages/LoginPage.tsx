import { Link } from 'react-router';

import { AuthLayout } from '@/components/AuthLayout';
import { LoginForm } from '@/features/auth/LoginForm';

export default function LoginPage() {
  return (
    <AuthLayout>
      <LoginForm
        portal="patient"
        title="Patient sign in"
        subtitle="Book appointments, message your doctor and track your visits."
        footer={
          <div className="stack small-gap small-text">
            <Link to="/forgot-password">Forgot your password?</Link>
            <span className="muted">
              New here? <Link to="/register">Create a patient account</Link>
            </span>
            <span className="muted">
              Hospital staff? <Link to="/staff/login">Staff sign in</Link>
            </span>
          </div>
        }
      />
    </AuthLayout>
  );
}
