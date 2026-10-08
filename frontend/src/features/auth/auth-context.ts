import { createContext } from 'react';

import type { Me } from '@/features/users/types';

import type { ChangePasswordInput, LoginInput, RegisterInput } from './types';

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated';

export interface AuthContextValue {
  status: AuthStatus;
  user: Me | undefined;
  login: (input: LoginInput) => Promise<Me>;
  register: (input: RegisterInput) => Promise<Me>;
  logout: () => Promise<void>;
  changePassword: (input: ChangePasswordInput) => Promise<Me>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
