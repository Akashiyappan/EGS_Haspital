import type { User } from '@/features/users/types';
import { api } from '@/lib/api-client';

import type { ChangePasswordInput, LoginInput, RegisterInput, TokenResponse } from './types';

export const authApi = {
  login: (input: LoginInput) => api.post<TokenResponse>('/auth/login', input).then((r) => r.data),
  register: (input: RegisterInput) => api.post<User>('/auth/register', input).then((r) => r.data),
  logout: () => api.post<void>('/auth/logout'),
  changePassword: (input: ChangePasswordInput) =>
    api.post<TokenResponse>('/auth/change-password', input).then((r) => r.data),
  forgotPassword: (email: string) =>
    api.post<{ message: string }>('/auth/forgot-password', { email }).then((r) => r.data),
  resetPassword: (token: string, newPassword: string) =>
    api
      .post<{ message: string }>('/auth/reset-password', { token, new_password: newPassword })
      .then((r) => r.data),
};
