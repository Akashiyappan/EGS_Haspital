import type { Role } from '@/lib/types';

export type Portal = 'patient' | 'staff';

export interface TokenResponse {
  access_token: string;
  token_type: 'bearer';
  expires_in: number;
  role: Role;
  must_change_password: boolean;
}

export interface LoginInput {
  email: string;
  password: string;
  portal: Portal;
}

export interface RegisterInput {
  first_name: string;
  last_name?: string;
  email: string;
  password: string;
}

export interface ChangePasswordInput {
  current_password: string;
  new_password: string;
}
