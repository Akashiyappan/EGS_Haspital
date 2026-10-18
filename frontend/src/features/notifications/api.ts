import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api-client';
import type { Notification, Page } from '@/lib/types';
import { withToast } from '@/lib/toast';

export const notificationKeys = {
  all: ['notifications'] as const,
  list: (page: number) => ['notifications', 'list', page] as const,
  unread: ['notifications', 'unread'] as const,
};

export function useNotifications(page = 1) {
  return useQuery({
    queryKey: notificationKeys.list(page),
    queryFn: () =>
      api
        .get<Page<Notification>>('/notifications', { params: { page, page_size: 10 } })
        .then((r) => r.data),
  });
}

export function useUnreadNotifications() {
  return useQuery({
    queryKey: notificationKeys.unread,
    queryFn: () => api.get<{ unread: number }>('/notifications/unread-count').then((r) => r.data),
    refetchInterval: 120_000, // fallback if the realtime channel is down
  });
}

export function useMarkNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation(
    withToast({
      mutationFn: (id: number | 'all') =>
        id === 'all' ? api.post('/notifications/read-all') : api.post(`/notifications/${id}/read`),
      successMessage: 'Notifications marked as read',
      onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
    })
  );
}
