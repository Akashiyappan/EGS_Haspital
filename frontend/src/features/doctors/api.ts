import { keepPreviousData, useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api-client';
import type { Availability, DaySlots, DoctorPublic, Page, Specialization } from '@/lib/types';

export const doctorKeys = {
  all: ['doctors'] as const,
  list: (params: object) => ['doctors', 'list', params] as const,
  detail: (id: number) => ['doctors', id] as const,
  slots: (id: number, date: string) => ['doctors', id, 'slots', date] as const,
  availability: (id: number, from: string) => ['doctors', id, 'availability', from] as const,
  specializations: ['specializations'] as const,
};

export interface DoctorSearch {
  page: number;
  search?: string;
  specialization_id?: number;
}

export function useSpecializations() {
  return useQuery({
    queryKey: doctorKeys.specializations,
    queryFn: () => api.get<Specialization[]>('/specializations').then((r) => r.data),
    staleTime: 5 * 60_000,
  });
}

export function useDoctors(params: DoctorSearch) {
  return useQuery({
    queryKey: doctorKeys.list(params),
    queryFn: () =>
      api
        .get<Page<DoctorPublic>>('/doctors', { params: { ...params, page_size: 12 } })
        .then((r) => r.data),
    placeholderData: keepPreviousData,
  });
}

export function useDoctor(id: number) {
  return useQuery({
    queryKey: doctorKeys.detail(id),
    queryFn: () => api.get<DoctorPublic>(`/doctors/${id}`).then((r) => r.data),
  });
}

export function useAvailability(id: number, from: string) {
  return useQuery({
    queryKey: doctorKeys.availability(id, from),
    queryFn: () =>
      api
        .get<Availability>(`/doctors/${id}/availability`, { params: { from, days: 14 } })
        .then((r) => r.data),
  });
}

export function useSlots(id: number, date: string | null) {
  return useQuery({
    queryKey: doctorKeys.slots(id, date ?? ''),
    queryFn: () =>
      api.get<DaySlots>(`/doctors/${id}/slots`, { params: { date } }).then((r) => r.data),
    enabled: !!date,
    refetchInterval: 60_000, // keep availability fresh while the patient decides
  });
}
