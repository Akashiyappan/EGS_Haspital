import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';

import { api } from '@/lib/api-client';
import { type RealtimeEvent, realtime } from '@/lib/realtime';
import type { Meta } from '@/lib/types';

const FALLBACK_META: Meta = {
  app_name: 'Onezae Health',
  clinic_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  appointment_duration_minutes: 30,
  cancellation_cutoff_hours: 2,
  booking_window_days: 60,
  upload_max_bytes: 5 * 1024 * 1024,
  upload_allowed_types: ['image/jpeg', 'image/png', 'image/webp'],
  uploads_enabled: false,
  ai_enabled: false,
};

/** Public client configuration (clinic timezone, limits, feature flags). */
export function useMeta(): Meta {
  const { data } = useQuery({
    queryKey: ['meta'],
    queryFn: () => api.get<Meta>('/meta').then((r) => r.data),
    staleTime: Infinity,
  });
  return data ?? FALLBACK_META;
}

export function useClinicTimezone(): string {
  return useMeta().clinic_timezone;
}

export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

/** Subscribe to realtime events of the given types. */
export function useRealtimeEvent(types: string[], handler: (event: RealtimeEvent) => void): void {
  const key = types.join('|');
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  });
  useEffect(() => {
    const wanted = new Set(key.split('|'));
    return realtime.subscribe((event) => {
      if (wanted.has(event.type)) handlerRef.current(event);
    });
  }, [key]);
}

export function useRealtimeState() {
  return useSyncExternalStore(
    (onChange) => realtime.onStateChange(onChange),
    () => realtime.state,
  );
}
