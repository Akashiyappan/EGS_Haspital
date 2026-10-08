import type { Role } from '@/lib/types';

export const HOME_BY_ROLE: Record<Role, string> = {
  ADMIN: '/admin',
  DOCTOR: '/doctor',
  PATIENT: '/patient',
};
