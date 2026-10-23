import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api-client';
import type { Prescription, PrescriptionCreatePayload, PrescriptionRequest } from '@/lib/types';

export const prescriptionKeys = {
  all: ['prescriptions'] as const,
  list: (filters: { patient_id?: number; doctor_id?: number; active_only?: boolean }) =>
    [...prescriptionKeys.all, 'list', filters] as const,
  detail: (id: number) => [...prescriptionKeys.all, 'detail', id] as const,
  appointment: (appointmentId: number) =>
    [...prescriptionKeys.all, 'appointment', appointmentId] as const,
};

export function usePrescriptionRequests() {
  return useQuery({ queryKey: [...prescriptionKeys.all, 'requests'], queryFn: () => api.get<PrescriptionRequest[]>('/prescriptions/requests').then(r => r.data) });
}

export function useCreatePrescriptionRequest() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (payload: { doctor_id: number; reason: string }) => api.post<PrescriptionRequest>('/prescriptions/requests', payload).then(r => r.data), onSuccess: () => { void client.invalidateQueries({ queryKey: [...prescriptionKeys.all, 'requests'] }); } });
}

export function useFulfillPrescriptionRequest() {
  const client = useQueryClient();
  return useMutation({ mutationFn: (id: number) => api.post(`/prescriptions/requests/${id}/fulfill`), onSuccess: () => { void client.invalidateQueries({ queryKey: [...prescriptionKeys.all, 'requests'] }); } });
}

export function usePrescriptions(filters: {
  patient_id?: number;
  doctor_id?: number;
  active_only?: boolean;
} = {}) {
  return useQuery({
    queryKey: prescriptionKeys.list(filters),
    queryFn: async () => {
      const response = await api.get<Prescription[]>('/prescriptions', { params: filters });
      return response.data;
    },
  });
}

export function usePrescription(id: number | null | undefined) {
  return useQuery({
    queryKey: prescriptionKeys.detail(id ?? 0),
    queryFn: async () => {
      if (!id) return null;
      const response = await api.get<Prescription>(`/prescriptions/${id}`);
      return response.data;
    },
    enabled: Boolean(id),
  });
}

export function useAppointmentPrescription(appointmentId: number | null | undefined) {
  return useQuery({
    queryKey: prescriptionKeys.appointment(appointmentId ?? 0),
    queryFn: async () => {
      if (!appointmentId) return null;
      const response = await api.get<Prescription | null>(
        `/prescriptions/appointment/${appointmentId}`,
      );
      return response.data;
    },
    enabled: Boolean(appointmentId),
  });
}

export function useCreatePrescription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PrescriptionCreatePayload) => {
      const response = await api.post<Prescription>('/prescriptions', payload);
      return response.data;
    },
    onSuccess: (prescription) => {
      void queryClient.invalidateQueries({ queryKey: prescriptionKeys.all });
      if (prescription.appointment_id) {
        void queryClient.invalidateQueries({
          queryKey: prescriptionKeys.appointment(prescription.appointment_id),
        });
      }
    },
  });
}

export function useUpdatePrescription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      payload,
    }: {
      id: number;
      payload: Partial<PrescriptionCreatePayload>;
    }) => {
      const response = await api.put<Prescription>(`/prescriptions/${id}`, payload);
      return response.data;
    },
    onSuccess: (prescription) => {
      void queryClient.invalidateQueries({ queryKey: prescriptionKeys.all });
      void queryClient.invalidateQueries({ queryKey: prescriptionKeys.detail(prescription.id) });
      if (prescription.appointment_id) {
        void queryClient.invalidateQueries({
          queryKey: prescriptionKeys.appointment(prescription.appointment_id),
        });
      }
    },
  });
}

export function useDeletePrescription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: number) => {
      await api.delete(`/prescriptions/${id}`);
      return id;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: prescriptionKeys.all });
    },
  });
}
