import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api-client';
import type { DoctorAdmin, Page, ScheduleRule, TimeOff } from '@/lib/types';

export interface DoctorPatient {
  id: number;
  first_name: string;
  last_name: string | null;
  full_name: string;
  email: string;
  phone: string | null;
  avatar_url: string | null;
  date_of_birth: string | null;
  gender: string | null;
  last_appointment_at: string | null;
  appointment_count: number | null;
}

export const doctorPortalKeys = {
  me: ['doctor', 'me'] as const,
  schedule: ['doctor', 'schedule'] as const,
  patients: (params: object) => ['doctor', 'patients', params] as const,
  patient: (id: number) => ['doctor', 'patient', id] as const,
};

export function useDoctorProfile() {
  return useQuery({
    queryKey: doctorPortalKeys.me,
    queryFn: () => api.get<DoctorAdmin>('/doctor/me').then((r) => r.data),
  });
}

export function useUpdateDoctorProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { bio?: string | null; qualification?: string | null }) =>
      api.patch<DoctorAdmin>('/doctor/me', input).then((r) => r.data),
    onSuccess: (doctor) => queryClient.setQueryData(doctorPortalKeys.me, doctor),
  });
}

export function useMySchedule() {
  return useQuery({
    queryKey: doctorPortalKeys.schedule,
    queryFn: () =>
      api
        .get<{ timezone: string; rules: ScheduleRule[]; time_off: TimeOff[] }>('/doctor/schedule')
        .then((r) => r.data),
  });
}

export function useMyPatients(params: { page: number; search?: string }) {
  return useQuery({
    queryKey: doctorPortalKeys.patients(params),
    queryFn: () => api.get<Page<DoctorPatient>>('/doctor/patients', { params }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });
}

export function useMyPatient(id: number) {
  return useQuery({
    queryKey: doctorPortalKeys.patient(id),
    queryFn: () => api.get<DoctorPatient>(`/doctor/patients/${id}`).then((r) => r.data),
  });
}
