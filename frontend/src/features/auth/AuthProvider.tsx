import { useQuery, useQueryClient } from '@tanstack/react-query';
import { type ReactNode, useCallback, useEffect, useMemo, useState } from 'react';

import { userKeys, usersApi } from '@/features/users/api';
import type { Me } from '@/features/users/types';
import { refreshAccessToken, setUnauthorizedHandler, tokenStore } from '@/lib/api-client';
import { realtime } from '@/lib/realtime';

import { authApi } from './api';
import { AuthContext, type AuthContextValue, type AuthStatus } from './auth-context';
import type { ChangePasswordInput, LoginInput, RegisterInput } from './types';

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<AuthStatus>('loading');

  // Restore the session from the httpOnly refresh cookie on first load.
  useEffect(() => {
    let cancelled = false;
    refreshAccessToken()
      .then(() => queryClient.fetchQuery({ queryKey: userKeys.me, queryFn: usersApi.me }))
      .then(() => !cancelled && setStatus('authenticated'))
      .catch(() => !cancelled && setStatus('unauthenticated'));

    setUnauthorizedHandler(() => {
      queryClient.clear();
      setStatus('unauthenticated');
    });
    return () => {
      cancelled = true;
      setUnauthorizedHandler(null);
    };
  }, [queryClient]);

  const { data: user } = useQuery({
    queryKey: userKeys.me,
    queryFn: usersApi.me,
    enabled: status === 'authenticated',
  });

  // Realtime runs only for fully signed-in users (not while a temporary
  // password still has to be changed).
  const realtimeEnabled = status === 'authenticated' && !!user && !user.must_change_password;
  useEffect(() => {
    if (!realtimeEnabled) return;
    realtime.start();
    return () => realtime.stop();
  }, [realtimeEnabled]);

  const loadMe = useCallback(
    () => queryClient.fetchQuery({ queryKey: userKeys.me, queryFn: usersApi.me, staleTime: 0 }),
    [queryClient],
  );

  const login = useCallback(
    async (input: LoginInput): Promise<Me> => {
      const { access_token } = await authApi.login(input);
      tokenStore.set(access_token);
      const me = await loadMe();
      setStatus('authenticated');
      return me;
    },
    [loadMe],
  );

  const register = useCallback(
    async (input: RegisterInput): Promise<Me> => {
      await authApi.register(input);
      return login({ email: input.email, password: input.password, portal: 'patient' });
    },
    [login],
  );

  const changePassword = useCallback(
    async (input: ChangePasswordInput): Promise<Me> => {
      const { access_token } = await authApi.changePassword(input);
      tokenStore.set(access_token);
      return loadMe();
    },
    [loadMe],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      realtime.stop();
      tokenStore.set(null);
      queryClient.clear();
      setStatus('unauthenticated');
    }
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, user, login, register, logout, changePassword }),
    [status, user, login, register, logout, changePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
