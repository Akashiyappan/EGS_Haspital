import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { AdminUser } from '@/features/users/types';
import { api } from '@/lib/api-client';
import type {
  DoctorAdmin,
  Page,
  Role,
  ScheduleRule,
  Specialization,
  TimeOff,
  TimeOffKind,
} from '@/lib/types';
import { withToast } from '@/lib/toast';

export const adminKeys = {
  all: ['admin'] as const,
  stats: ['admin', 'stats'] as const,
  doctors: (params: object) => ['admin', 'doctors', params] as const,
  doctor: (id: number) => ['admin', 'doctor', id] as const,
  schedule: (id: number) => ['admin', 'doctor', id, 'schedule'] as const,
  timeOff: (id: number | 'clinic') => ['admin', 'time-off', id] as const,
  specializations: ['admin', 'specializations'] as const,
  users: (params: object) => ['admin', 'users', params] as const,
  audit: (params: object) => ['admin', 'audit', params] as const,
};

export interface AdminStats {
  doctors_active: number;
  doctors_inactive: number;
  patients: number;
  appointments_today: number;
  appointments_upcoming: number;
  appointments_by_status: Record<string, number>;
}

export interface DoctorInput {
  first_name: string;
  last_name?: string | null;
  email?: string;
  temporary_password?: string;
  phone?: string | null;
  specialization_ids: number[];
  qualification?: string | null;
  experience_years: number;
  bio?: string | null;
  is_active?: boolean;
}

export interface AuditLog {
  id: number;
  actor_id: number | null;
  actor_name: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  request_id: string | null;
  created_at: string;
}

function useInvalidateAdmin() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: adminKeys.all });
}

export function useAdminStats() {
  return useQuery({
    queryKey: adminKeys.stats,
    queryFn: () => api.get<AdminStats>('/admin/stats').then((r) => r.data),
  });
}

export function useAdminDoctors(params: {
  page: number;
  search?: string;
  specialization_id?: number;
  is_active?: boolean;
}) {
  return useQuery({
    queryKey: adminKeys.doctors(params),
    queryFn: () => api.get<Page<DoctorAdmin>>('/admin/doctors', { params }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });
}

export function useAdminDoctor(id: number) {
  return useQuery({
    queryKey: adminKeys.doctor(id),
    queryFn: () => api.get<DoctorAdmin>(`/admin/doctors/${id}`).then((r) => r.data),
  });
}

export function useSaveDoctor(id?: number) {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: (input: DoctorInput) =>
        (id
          ? api.patch<DoctorAdmin>(`/admin/doctors/${id}`, input)
          : api.post<DoctorAdmin>('/admin/doctors', input)
        ).then((r) => r.data),
      successMessage: id ? 'Doctor updated successfully' : 'Doctor created successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useDoctorStatus(id: number) {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: (input: { is_active: boolean; reason?: string }) =>
        api
          .post<{ doctor: DoctorAdmin; cancelled_appointments: number }>(
            `/admin/doctors/${id}/status`,
            input,
          )
          .then((r) => r.data),
      successMessage: (data) =>
        data.doctor.is_active ? 'Doctor activated successfully' : 'Doctor deactivated successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useDeleteDoctor(id: number) {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: () => api.delete(`/admin/doctors/${id}`),
      successMessage: 'Doctor deleted successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useResetDoctorPassword(id: number) {
  return useMutation(
    withToast({
      mutationFn: (temporaryPassword: string) =>
        api.post(`/admin/doctors/${id}/reset-password`, { temporary_password: temporaryPassword }),
      successMessage: 'Password reset successfully',
    })
  );
}

export function useUploadDoctorAvatar(id: number) {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: (file: File) => {
        const form = new FormData();
        form.append('file', file);
        return api
          .post<DoctorAdmin>(`/admin/doctors/${id}/avatar`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
          .then((r) => r.data);
      },
      successMessage: 'Avatar uploaded successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useDoctorSchedule(id: number) {
  return useQuery({
    queryKey: adminKeys.schedule(id),
    queryFn: () =>
      api
        .get<{ timezone: string; rules: ScheduleRule[] }>(`/admin/doctors/${id}/schedule`)
        .then((r) => r.data),
  });
}

export function useSaveSchedule(id: number) {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: (rules: ScheduleRule[]) =>
        api
          .put<{ timezone: string; rules: ScheduleRule[]; conflicting_appointment_ids: number[] }>(
            `/admin/doctors/${id}/schedule`,
            { rules },
          )
          .then((r) => r.data),
      successMessage: 'Schedule saved successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useTimeOff(doctorId: number | 'clinic') {
  return useQuery({
    queryKey: adminKeys.timeOff(doctorId),
    queryFn: () =>
      api
        .get<TimeOff[]>(
          doctorId === 'clinic' ? '/admin/time-off' : `/admin/doctors/${doctorId}/time-off`,
        )
        .then((r) => r.data),
  });
}

export function useAddTimeOff(doctorId: number | 'clinic') {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: (input: {
        kind: TimeOffKind;
        starts_at: string;
        ends_at: string;
        reason?: string;
      }) =>
        api
          .post<TimeOff & { conflicting_appointment_ids: number[] }>(
            doctorId === 'clinic' ? '/admin/time-off' : `/admin/doctors/${doctorId}/time-off`,
            input,
          )
          .then((r) => r.data),
      successMessage: 'Time off added successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useRemoveTimeOff() {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: (id: number) => api.delete(`/admin/time-off/${id}`),
      successMessage: 'Time off removed successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useAdminSpecializations() {
  return useQuery({
    queryKey: adminKeys.specializations,
    queryFn: () => api.get<Specialization[]>('/admin/specializations').then((r) => r.data),
  });
}

export function useSaveSpecialization() {
  const invalidate = useInvalidateAdmin();
  const queryClient = useQueryClient();
  return useMutation(
    withToast({
      mutationFn: ({
        id,
        ...input
      }: {
        id?: number;
        name?: string;
        description?: string | null;
        is_active?: boolean;
      }) =>
        (id
          ? api.patch<Specialization>(`/admin/specializations/${id}`, input)
          : api.post<Specialization>('/admin/specializations', input)
        ).then((r) => r.data),
      successMessage: (data) => (data.id ? 'Specialization updated successfully' : 'Specialization created successfully'),
      onSuccess: () => {
        void invalidate();
        void queryClient.invalidateQueries({ queryKey: ['specializations'] });
      },
    })
  );
}

export function useAdminUsers(params: {
  page: number;
  role?: Role;
  search?: string;
  is_active?: boolean;
}) {
  return useQuery({
    queryKey: adminKeys.users(params),
    queryFn: () => api.get<Page<AdminUser>>('/admin/users', { params }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });
}

export function useUserStatus() {
  const invalidate = useInvalidateAdmin();
  return useMutation(
    withToast({
      mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
        api.post<AdminUser>(`/admin/users/${id}/status`, { is_active }).then((r) => r.data),
      successMessage: (data) =>
        data.is_active ? 'User activated successfully' : 'User deactivated successfully',
      onSuccess: () => invalidate(),
    })
  );
}

export function useAuditLogs(params: { page: number; action?: string }) {
  return useQuery({
    queryKey: adminKeys.audit(params),
    queryFn: () => api.get<Page<AuditLog>>('/admin/audit-logs', { params }).then((r) => r.data),
    placeholderData: keepPreviousData,
  });
}
