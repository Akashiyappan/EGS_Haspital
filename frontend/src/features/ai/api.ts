import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { appointmentKeys } from '@/features/appointments/api';
import { api } from '@/lib/api-client';
import type { DoctorPublic, Page } from '@/lib/types';
import { withToast } from '@/lib/toast';

export type Urgency = 'emergency' | 'urgent' | 'routine' | 'self_care';

export interface AIResult {
  summary: string;
  response_type?: 'assessment' | 'follow_up' | 'appointment';
  urgency: Urgency;
  possible_concerns: string[];
  recommended_specializations: string[];
  recommended_doctor_ids: number[];
  next_steps: string[];
  follow_up_questions: string[];
  emergency_message: string | null;
  disclaimer: string;
  recommended_doctors: DoctorPublic[];
  tools_used: string[];
  appointment_confirmation?: {
    id: number;
    doctor_id: number;
    doctor_name: string;
    starts_at: string;
    status: string;
  } | null;
  appointment_options?: {
    doctor_id: number;
    doctor_name: string;
    specialization: string;
    starts_at: string;
    local_time: string;
  }[];
  doctor_directory?: DoctorPublic[];
}

export interface AIMessage {
  id: number;
  role: 'USER' | 'ASSISTANT';
  content: string;
  result: AIResult | null;
  created_at: string;
}

export interface AIExchange {
  user_message: AIMessage;
  assistant_message: AIMessage;
}

export interface AIConversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export const aiKeys = {
  conversations: ['ai', 'conversations'] as const,
  messages: (id: number) => ['ai', 'messages', id] as const,
};

export function useAIConversations() {
  return useQuery({
    queryKey: aiKeys.conversations,
    queryFn: () =>
      api
        .get<Page<AIConversation>>('/ai/conversations', { params: { page_size: 50 } })
        .then((r) => r.data),
  });
}

export function useAIMessages(conversationId: number | null) {
  return useQuery({
    queryKey: aiKeys.messages(conversationId ?? 0),
    queryFn: () =>
      api.get<AIMessage[]>(`/ai/conversations/${conversationId}/messages`).then((r) => r.data),
    enabled: conversationId !== null,
  });
}

export function useCreateAIConversation() {
  const queryClient = useQueryClient();
  return useMutation(
    withToast({
      mutationFn: () => api.post<AIConversation>('/ai/conversations', {}).then((r) => r.data),
      successMessage: 'New conversation started',
      onSuccess: () => queryClient.invalidateQueries({ queryKey: aiKeys.conversations }),
    })
  );
}

export function useDeleteAIConversation() {
  const queryClient = useQueryClient();
  return useMutation(
    withToast({
      mutationFn: (id: number) => api.delete(`/ai/conversations/${id}`),
      successMessage: 'Conversation deleted',
      onSuccess: () => queryClient.invalidateQueries({ queryKey: aiKeys.conversations }),
    })
  );
}

export function useAskAssistant(conversationId: number) {
  const queryClient = useQueryClient();
  return useMutation(
    withToast({
      mutationFn: (content: string) =>
        api
          .post<AIExchange>(
            `/ai/conversations/${conversationId}/messages`,
            { content },
            { timeout: 90_000 },
          )
          .then((r) => r.data),
      successMessage: 'Response received',
      onSuccess: (exchange) => {
        queryClient.setQueryData<AIMessage[]>(aiKeys.messages(conversationId), (previous = []) => [
          ...previous,
          exchange.user_message,
          exchange.assistant_message,
        ]);
        void queryClient.invalidateQueries({ queryKey: aiKeys.conversations });
        if (exchange.assistant_message.result?.appointment_confirmation) {
          void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
        }
      },
    })
  );
}

export function useBookFromAssistant(conversationId: number) {
  const queryClient = useQueryClient();
  return useMutation(
    withToast({
      mutationFn: (slot: { doctor_id: number; starts_at: string }) =>
        api
          .post<AIExchange>(`/ai/conversations/${conversationId}/book`, slot)
          .then((response) => response.data),
      successMessage: 'Appointment booked',
      onSuccess: (exchange, slot) => {
        queryClient.setQueryData<AIMessage[]>(aiKeys.messages(conversationId), (previous = []) => [
          ...previous.map((message) => {
            if (!message.result?.appointment_options) return message;
            return {
              ...message,
              result: {
                ...message.result,
                appointment_options: message.result.appointment_options.filter(
                  (option) =>
                    option.doctor_id !== slot.doctor_id || option.starts_at !== slot.starts_at,
                ),
              },
            };
          }),
          exchange.user_message,
          exchange.assistant_message,
        ]);
        void queryClient.invalidateQueries({ queryKey: aiKeys.conversations });
        void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
      },
    }),
  );
}
