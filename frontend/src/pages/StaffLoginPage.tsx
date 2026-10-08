import { Link } from 'react-router';

import { AuthLayout } from '@/components/AuthLayout';
import { LoginForm } from '@/features/auth/LoginForm';

export default function StaffLoginPage() {
  return (
    <AuthLayout variant="staff">
      <LoginForm
        portal="staff"
        title="Staff sign in"
        subtitle="For administrators and doctors. Accounts are issued by the hospital."
        footer={
          <div className="stack small-gap small-text">
            <Link to="/forgot-password">Forgot your password?</Link>
            <span className="muted">
              Are you a patient? <Link to="/login">Patient sign in</Link>
            </span>
          </div>
        }
      />
    </AuthLayout>
  );
}
