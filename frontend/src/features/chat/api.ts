import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api-client';
import type { Page } from '@/lib/types';
import { withToast } from '@/lib/toast';

export interface Counterpart {
  user_id: number;
  doctor_id: number | null;
  patient_id: number | null;
  full_name: string;
  avatar_url: string | null;
  role: 'DOCTOR' | 'PATIENT';
  online: boolean;
}

export interface Attachment {
  id: number;
  url: string;
  content_type: string;
  width: number | null;
  height: number | null;
  bytes: number;
}

export interface ChatMessage {
  id: number;
  conversation_id: number;
  sender_id: number;
  message_type: 'TEXT' | 'IMAGE';
  body: string | null;
  client_id: string | null;
  attachments: Attachment[];
  created_at: string;
}

export interface Conversation {
  id: number;
  counterpart: Counterpart;
  last_message: ChatMessage | null;
  last_message_at: string | null;
  unread_count: number;
}

export interface MessagePage {
  items: ChatMessage[];
  has_more: boolean;
}

export const chatKeys = {
  all: ['chat'] as const,
  conversations: ['chat', 'conversations'] as const,
  unread: ['chat', 'unread'] as const,
};

export const chatApi = {
  messages: (conversationId: number, params: { before_id?: number; after_id?: number }) =>
    api
      .get<MessagePage>(`/chat/conversations/${conversationId}/messages`, {
        params: { ...params, limit: 50 },
      })
      .then((r) => r.data),
  sendText: (conversationId: number, body: string, clientId: string) =>
    api
      .post<ChatMessage>(`/chat/conversations/${conversationId}/messages`, {
        body,
        client_id: clientId,
      })
      .then((r) => r.data),
  sendImage: (conversationId: number, file: File, caption: string, clientId: string) => {
    const form = new FormData();
    form.append('file', file);
    if (caption) form.append('caption', caption);
    form.append('client_id', clientId);
    return api
      .post<ChatMessage>(`/chat/conversations/${conversationId}/images`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 60_000,
      })
      .then((r) => r.data);
  },
  markRead: (conversationId: number, messageId: number) =>
    api.post(`/chat/conversations/${conversationId}/read`, { message_id: messageId }),
};

export function useConversations() {
  return useQuery({
    queryKey: chatKeys.conversations,
    queryFn: () =>
      api
        .get<Page<Conversation>>('/chat/conversations', { params: { page_size: 50 } })
        .then((r) => r.data),
  });
}

export function useChatUnread() {
  return useQuery({
    queryKey: chatKeys.unread,
    queryFn: () => api.get<{ unread: number }>('/chat/unread-count').then((r) => r.data),
    refetchInterval: 120_000,
  });
}

export function useOpenConversation() {
  const queryClient = useQueryClient();
  return useMutation(
    withToast({
      mutationFn: (input: { doctor_id?: number; patient_id?: number }) =>
        api.post<Conversation>('/chat/conversations', input).then((r) => r.data),
      successMessage: 'Conversation started',
      onSuccess: () => queryClient.invalidateQueries({ queryKey: chatKeys.conversations }),
    })
  );
}

export function newClientId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
