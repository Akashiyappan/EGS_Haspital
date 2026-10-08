import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { createMemoryRouter, RouterProvider, type RouteObject } from 'react-router';
import { vi } from 'vitest';

import { AuthContext, type AuthContextValue } from '@/features/auth/auth-context';
import type { Me } from '@/features/users/types';
import type { Meta, Role } from '@/lib/types';

export const META: Meta = {
  app_name: 'Onezae Health API',
  clinic_timezone: 'Asia/Kolkata',
  appointment_duration_minutes: 30,
  cancellation_cutoff_hours: 2,
  booking_window_days: 60,
  upload_max_bytes: 5 * 1024 * 1024,
  upload_allowed_types: ['image/jpeg', 'image/png', 'image/webp'],
  uploads_enabled: true,
  ai_enabled: true,
};

export function makeUser(role: Role, overrides: Partial<Me> = {}): Me {
  return {
    id: 1,
    email: `${role.toLowerCase()}@example.com`,
    role,
    first_name: 'Test',
    last_name: 'User',
    full_name: 'Test User',
    phone: null,
    avatar_url: null,
    is_active: true,
    must_change_password: false,
    created_at: '2030-01-01T00:00:00Z',
    patient: null,
    doctor_id: null,
    ...overrides,
  };
}

export function makeAuth(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    status: 'unauthenticated',
    user: undefined,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
    ...overrides,
  };
}

export function createTestQueryClient(): QueryClient {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  });
  client.setQueryData(['meta'], META);
  return client;
}

/** Render routes inside query, auth and router providers. */
export function renderRoutes(
  routes: RouteObject[],
  {
    initialPath = '/',
    auth = makeAuth(),
    queryClient = createTestQueryClient(),
  }: { initialPath?: string; auth?: AuthContextValue; queryClient?: QueryClient } = {},
) {
  const router = createMemoryRouter(routes, { initialEntries: [initialPath] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <AuthContext.Provider value={auth}>
        <RouterProvider router={router} />
      </AuthContext.Provider>
    </QueryClientProvider>,
  );
  return { ...view, router, queryClient };
}

export function renderPage(ui: ReactElement, options: Parameters<typeof renderRoutes>[1] = {}) {
  return renderRoutes([{ path: '*', element: ui }], options);
}

/** Build an axios-like error for mocked API failures. */
export function apiError(status: number, code: string, message: string) {
  return Object.assign(new Error(message), {
    isAxiosError: true,
    response: { status, data: { error: { code, message } } },
  });
}
