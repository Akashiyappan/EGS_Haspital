import {
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
  useId,
} from 'react';

interface FieldShellProps {
  label: string;
  hint?: ReactNode;
  error?: string | null;
}

function FieldShell({
  id,
  label,
  hint,
  error,
  children,
}: FieldShellProps & { id: string; children: ReactNode }) {
  return (
    <div className={error ? 'field has-error' : 'field'}>
      <label htmlFor={id}>{label}</label>
      {children}
      {error ? (
        <span id={`${id}-error`} className="field-error" role="alert">
          {error}
        </span>
      ) : (
        hint && (
          <span id={`${id}-hint`} className="field-hint">
            {hint}
          </span>
        )
      )}
    </div>
  );
}

function describedBy(id: string, error?: string | null, hint?: ReactNode) {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

type FormFieldProps = FieldShellProps & InputHTMLAttributes<HTMLInputElement>;

export function FormField({ label, hint, error, id, ...inputProps }: FormFieldProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error}>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, error, hint)}
        {...inputProps}
      />
    </FieldShell>
  );
}

type TextAreaFieldProps = FieldShellProps & TextareaHTMLAttributes<HTMLTextAreaElement>;

export function TextAreaField({ label, hint, error, id, ...props }: TextAreaFieldProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error}>
      <textarea
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, error, hint)}
        {...props}
      />
    </FieldShell>
  );
}

type SelectFieldProps = FieldShellProps &
  SelectHTMLAttributes<HTMLSelectElement> & { children: ReactNode };

export function SelectField({ label, hint, error, id, children, ...props }: SelectFieldProps) {
  const generated = useId();
  const inputId = id ?? generated;
  return (
    <FieldShell id={inputId} label={label} hint={hint} error={error}>
      <select
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy(inputId, error, hint)}
        {...props}
      >
        {children}
      </select>
    </FieldShell>
  );
}
