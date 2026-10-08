import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { env } from '@/config/env';
import type { TokenResponse } from '@/features/auth/types';

/**
 * The access token lives only in memory (never localStorage) to limit XSS exposure.
 * The long-lived refresh token is an httpOnly cookie managed by the API.
 */
let accessToken: string | null = null;

export const tokenStore = {
  get: () => accessToken,
  set: (token: string | null) => {
    accessToken = token;
  },
};

export const api = axios.create({
  baseURL: env.apiBaseUrl,
  withCredentials: true,
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

let refreshPromise: Promise<string> | null = null;

/** Exchanges the refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshAccessToken(): Promise<string> {
  refreshPromise ??= axios
    .post<TokenResponse>(`${env.apiBaseUrl}/auth/refresh`, null, { withCredentials: true })
    .then(({ data }) => {
      tokenStore.set(data.access_token);
      return data.access_token;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

let unauthorizedHandler: (() => void) | null = null;

/** Called when the session can't be recovered (refresh failed). */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

const SKIP_REFRESH = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/logout'];

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;
    const shouldRefresh =
      error.response?.status === 401 &&
      original &&
      !original._retried &&
      !SKIP_REFRESH.some((path) => original.url?.startsWith(path));

    if (!shouldRefresh) {
      return Promise.reject(error);
    }

    original._retried = true;
    try {
      await refreshAccessToken();
      return await api(original);
    } catch {
      tokenStore.set(null);
      unauthorizedHandler?.();
      return Promise.reject(error);
    }
  },
);
