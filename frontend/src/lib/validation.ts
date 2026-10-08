/** Client-side checks that mirror the API's rules for immediate feedback.
 * The API remains the authority and re-validates everything. */

export type Errors<T extends string> = Partial<Record<T, string>>;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const PHONE_RE = /^\+?[0-9][0-9 ()-]{6,19}$/;

export function validateEmail(value: string): string | undefined {
  if (!value.trim()) return 'Email is required';
  if (!EMAIL_RE.test(value.trim())) return 'Enter a valid email address';
  return undefined;
}

export function validatePassword(value: string): string | undefined {
  if (value.length < 8) return 'Use at least 8 characters';
  if (new TextEncoder().encode(value).length > 72) return 'Password is too long';
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
    return 'Include at least one letter and one number';
  }
  return undefined;
}

export function validateRequired(value: string, label: string): string | undefined {
  return value.trim() ? undefined : `${label} is required`;
}

export function validatePhone(value: string): string | undefined {
  if (!value.trim()) return undefined;
  return PHONE_RE.test(value.trim()) ? undefined : 'Enter a valid phone number';
}

export function hasErrors<T extends string>(errors: Errors<T>): boolean {
  return Object.values(errors).some(Boolean);
}
