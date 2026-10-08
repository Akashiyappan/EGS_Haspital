import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { doctorKeys } from '@/features/doctors/api';
import { api } from '@/lib/api-client';
import type { Appointment, AppointmentAction, AppointmentStatus, Page } from '@/lib/types';

export const appointmentKeys = {
  all: ['appointments'] as const,
  list: (params: object) => ['appointments', 'list', params] as const,
};

export interface AppointmentQuery {
  page?: number;
  page_size?: number;
  scope?: 'upcoming' | 'past' | 'all';
  status?: AppointmentStatus;
  date_from?: string;
  date_to?: string;
  doctor_id?: number;
  patient_id?: number;
}

export function useAppointments(params: AppointmentQuery) {
  return useQuery({
    queryKey: appointmentKeys.list(params),
    queryFn: () => api.get<Page<Appointment>>('/appointments', { params }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });
}

export function useBookAppointment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { doctor_id: number; starts_at: string; reason?: string }) =>
      api.post<Appointment>('/appointments', input).then((r) => r.data),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      void queryClient.invalidateQueries({ queryKey: doctorKeys.all });
    },
  });
}

const ACTION_PATH: Record<AppointmentAction, string> = {
  confirm: 'confirm',
  cancel: 'cancel',
  complete: 'complete',
  no_show: 'no-show',
};

export function useAppointmentAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      action,
      reason,
      doctor_notes,
    }: {
      id: number;
      action: AppointmentAction;
      reason?: string;
      doctor_notes?: string;
    }) => {
      const body =
        action === 'cancel' ? { reason } : action === 'complete' ? { doctor_notes } : undefined;
      return api
        .post<Appointment>(`/appointments/${id}/${ACTION_PATH[action]}`, body)
        .then((r) => r.data);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      void queryClient.invalidateQueries({ queryKey: doctorKeys.all });
    },
  });
}
