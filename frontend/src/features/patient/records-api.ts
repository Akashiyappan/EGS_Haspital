import { useQuery } from '@tanstack/react-query';

import { api } from '@/lib/api-client';

export interface VisitRecord {
  appointment_id: number;
  date: string;
  doctor_name: string;
  specializations: string[];
  reason: string | null;
  clinical_notes: string | null;
}

export function useVisitRecords() {
  return useQuery({
    queryKey: ['patient-records', 'visits'],
    queryFn: () => api.get<VisitRecord[]>('/records/visits').then((response) => response.data),
  });
}
