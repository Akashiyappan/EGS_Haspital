import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { NotificationBell } from '@/components/NotificationBell';
import { makeAuth, makeUser, renderPage } from '@/test/utils';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api,
  tokenStore: { get: () => 'token', set: vi.fn() },
  refreshAccessToken: vi.fn().mockResolvedValue('token'),
  setUnauthorizedHandler: vi.fn(),
}));

const mockNotification = {
  id: 10,
  type: 'APPOINTMENT_CONFIRMED',
  title: 'Appointment Confirmed',
  body: 'Your appointment on May 10 is confirmed.',
  data: { appointment_id: 101 },
  read_at: null,
  created_at: new Date().toISOString(),
};

describe('NotificationBell', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.get.mockImplementation((url: string) => {
      if (url === '/notifications/unread-count') {
        return Promise.resolve({ data: { unread: 1 } });
      }
      if (url.startsWith('/notifications')) {
        return Promise.resolve({
          data: { items: [mockNotification], total: 1, page: 1, page_size: 20, pages: 1 },
        });
      }
      return Promise.resolve({ data: {} });
    });
    api.post.mockResolvedValue({ data: null });
  });

  it('displays unread notification badge and opens popover on click', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    renderPage(<NotificationBell />, { auth });

    const bellButton = await screen.findByRole('button', { name: /Notifications \(1 unread\)/ });
    expect(bellButton).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();

    await userEvent.click(bellButton);

    const dialog = screen.getByRole('dialog', { name: 'Notifications' });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByText('Appointment Confirmed')).toBeInTheDocument();
    expect(screen.getByText('Your appointment on May 10 is confirmed.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark all read' })).toBeInTheDocument();
  });

  it('marks a single notification as read when clicked', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    renderPage(<NotificationBell />, { auth });

    await userEvent.click(await screen.findByRole('button', { name: /Notifications/ }));
    const itemButton = screen.getByRole('button', { name: /Appointment Confirmed/ });
    await userEvent.click(itemButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/notifications/10/read');
    });
  });

  it('marks all notifications as read when "Mark all read" is clicked', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    renderPage(<NotificationBell />, { auth });

    await userEvent.click(await screen.findByRole('button', { name: /Notifications/ }));
    const markAllButton = screen.getByRole('button', { name: 'Mark all read' });
    await userEvent.click(markAllButton);

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/notifications/read-all');
    });
  });
});
