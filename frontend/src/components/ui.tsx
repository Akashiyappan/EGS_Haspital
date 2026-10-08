import { type ReactNode, useEffect, useId, useRef } from 'react';

import { getErrorMessage } from '@/lib/errors';
import type { AppointmentStatus } from '@/lib/types';

import { Icon, type IconName } from './Icon';
import { Spinner } from './Spinner';

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions && <div className="row wrap">{actions}</div>}
    </header>
  );
}

export function Card({
  title,
  actions,
  children,
  className = '',
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {(title || actions) && (
        <div className="panel-header">
          {title && <h2>{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const STATUS_LABEL: Record<AppointmentStatus, string> = {
  BOOKED: 'Booked',
  CONFIRMED: 'Confirmed',
  CANCELLED: 'Cancelled',
  COMPLETED: 'Completed',
  NO_SHOW: 'No-show',
};

export function StatusBadge({ status }: { status: AppointmentStatus }) {
  return <span className={`badge badge-${status.toLowerCase()}`}>{STATUS_LABEL[status]}</span>;
}

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function EmptyState({
  icon = 'list',
  title,
  description,
  action,
}: {
  icon?: IconName;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon">
        <Icon name={icon} size={28} />
      </span>
      <h3>{title}</h3>
      {description && <p className="muted">{description}</p>}
      {action}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="alert row space-between" role="alert">
      <span>{getErrorMessage(error)}</span>
      {onRetry && (
        <button type="button" className="secondary small" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function LoadingBlock({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading-block">
      <Spinner label={label} />
    </div>
  );
}

/** Standard loading / error / empty handling for a query result. */
export function QueryState({
  isLoading,
  error,
  isEmpty,
  empty,
  onRetry,
  children,
}: {
  isLoading: boolean;
  error: unknown;
  isEmpty?: boolean;
  empty?: ReactNode;
  onRetry?: () => void;
  children: ReactNode;
}) {
  if (isLoading) return <LoadingBlock />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (isEmpty) return <>{empty}</>;
  return <>{children}</>;
}

export function Alert({
  tone = 'error',
  children,
}: {
  tone?: 'error' | 'success' | 'info' | 'warning';
  children: ReactNode;
}) {
  const className = tone === 'error' ? 'alert' : tone;
  return (
    <div className={className} role={tone === 'error' ? 'alert' : 'status'}>
      {children}
    </div>
  );
}

export function Pagination({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (page: number) => void;
}) {
  if (pages <= 1) return null;
  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="secondary small"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
      >
        <Icon name="chevronLeft" size={16} /> Previous
      </button>
      <span className="muted">
        Page {page} of {pages}
      </span>
      <button
        type="button"
        className="secondary small"
        disabled={page >= pages}
        onClick={() => onChange(page + 1)}
      >
        Next <Icon name="chevronRight" size={16} />
      </button>
    </nav>
  );
}

export function Avatar({
  name,
  url,
  size = 40,
}: {
  name: string;
  url?: string | null;
  size?: number;
}) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
  return url ? (
    <img className="avatar" src={url} alt="" width={size} height={size} />
  ) : (
    <span className="avatar avatar-fallback" style={{ width: size, height: size }} aria-hidden>
      {initials || '?'}
    </span>
  );
}

export function Modal({
  title,
  open,
  onClose,
  children,
  footer,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal?.();
    if (!open && dialog.open) dialog.close?.();
  }, [open]);

  if (!open) return null;
  return (
    <dialog
      ref={dialogRef}
      className="modal"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      open
    >
      <div className="modal-header">
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="ghost icon-button" onClick={onClose} aria-label="Close">
          <Icon name="close" />
        </button>
      </div>
      <div className="modal-body">{children}</div>
      {footer && <div className="modal-footer">{footer}</div>}
    </dialog>
  );
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.value}
          type="button"
          role="tab"
          aria-selected={tab.value === value}
          className={tab.value === value ? 'tab active' : 'tab'}
          onClick={() => onChange(tab.value)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: ReactNode;
  icon: IconName;
}) {
  return (
    <div className="stat-card">
      <span className="stat-icon">
        <Icon name={icon} />
      </span>
      <div>
        <div className="stat-value">{value}</div>
        <div className="muted small-text">{label}</div>
      </div>
    </div>
  );
}
