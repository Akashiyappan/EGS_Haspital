import type { ReactNode } from 'react';

import { useMeta } from '@/lib/hooks';

import { Icon } from './Icon';

export function AuthLayout({
  children,
  variant = 'patient',
}: {
  children: ReactNode;
  variant?: 'patient' | 'staff';
}) {
  const meta = useMeta();
  return (
    <div className={`auth-page auth-${variant}`}>
      <div className="auth-brand">
        <span className="brand-mark">
          <Icon name="shield" size={18} />
        </span>
        <span>{meta.app_name.replace(/ API$/, '')}</span>
        {variant === 'staff' && <span className="role-pill">Staff portal</span>}
      </div>
      {children}
    </div>
  );
}
