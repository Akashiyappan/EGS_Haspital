import type { Role } from '@/lib/types';

export interface User {
  id: number;
  email: string;
  role: Role;
  first_name: string;
  last_name: string | null;
  full_name: string;
  phone: string | null;
  avatar_url: string | null;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface PatientProfile {
  id: number;
  date_of_birth: string | null;
  gender: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
}

export interface Me extends User {
  patient: PatientProfile | null;
  doctor_id: number | null;
}

export interface ProfileUpdate {
  first_name?: string;
  last_name?: string | null;
  phone?: string | null;
  date_of_birth?: string | null;
  gender?: string | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
}

export interface AdminUser extends User {
  last_login_at: string | null;
  deleted_at: string | null;
}
