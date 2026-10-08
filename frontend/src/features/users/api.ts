import { useMutation, useQueryClient } from '@tanstack/react-query';

import { api } from '@/lib/api-client';

import type { Me, ProfileUpdate } from './types';

export const userKeys = {
  me: ['users', 'me'] as const,
};

export const usersApi = {
  me: () => api.get<Me>('/users/me').then((r) => r.data),
  updateMe: (input: ProfileUpdate) => api.patch<Me>('/users/me', input).then((r) => r.data),
  uploadAvatar: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api
      .post<Me>('/users/me/avatar', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data);
  },
  deleteAvatar: () => api.delete('/users/me/avatar'),
};

export function useUpdateMe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: usersApi.updateMe,
    onSuccess: (user) => queryClient.setQueryData(userKeys.me, user),
  });
}

export function useUploadAvatar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: usersApi.uploadAvatar,
    onSuccess: (user) => queryClient.setQueryData(userKeys.me, user),
  });
}
