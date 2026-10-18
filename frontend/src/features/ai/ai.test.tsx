import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { makeAuth, makeUser, renderRoutes } from '@/test/utils';

import { AssistantView } from './AssistantView';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api,
  tokenStore: { get: () => 'token', set: vi.fn() },
  refreshAccessToken: vi.fn().mockResolvedValue('token'),
  setUnauthorizedHandler: vi.fn(),
}));

const mockAIConversation = {
  id: 1,
  title: 'Fever and headache',
  created_at: '2030-05-01T10:00:00Z',
  updated_at: '2030-05-01T10:05:00Z',
};

const mockAIMessage = {
  id: 1,
  conversation_id: 1,
  role: 'USER',
  content: 'I have had a high fever since yesterday',
  result: null,
  created_at: '2030-05-01T10:00:00Z',
};

describe('AssistantView', () => {
  beforeEach(() => {
    Object.values(api).forEach((fn) => fn.mockReset());
    api.get.mockImplementation((url: string) => {
      if (url === '/meta') {
        return Promise.resolve({
          data: {
            app_name: 'Onezae Health',
            clinic_timezone: 'Asia/Kolkata',
            upload_max_bytes: 5242880,
            upload_allowed_types: ['image/jpeg', 'image/png'],
            uploads_enabled: true,
            ai_enabled: true,
          },
        });
      }
      if (url === '/ai/conversations') {
        return Promise.resolve({
          data: { items: [mockAIConversation], total: 1, page: 1, page_size: 50, pages: 1 },
        });
      }
      if (url === '/ai/conversations/1/messages') {
        return Promise.resolve({
          data: [mockAIMessage],
        });
      }
      return Promise.resolve({ data: {} });
    });
  });

  it('renders initial state without selected conversation', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    renderRoutes(
      [{ path: '/patient/assistant', element: <AssistantView conversationId={null} /> }],
      { initialPath: '/patient/assistant', auth },
    );

    expect(await screen.findByText('Describe your symptoms')).toBeInTheDocument();
    expect(screen.getByText('Start a consultation')).toBeInTheDocument();
    expect(await screen.findByText('Fever and headache')).toBeInTheDocument();
  });

  it('renders messages for selected conversation and allows sending new message', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    api.post.mockResolvedValue({
      data: {
        user_message: { id: 2, role: 'USER', content: 'What medicine should I take?' },
        assistant_message: {
          id: 3,
          role: 'ASSISTANT',
          content: 'You should consult a physician.',
          result: {
            summary: 'Fever and headaches can indicate viral illness.',
            urgency: 'routine',
            possible_concerns: ['Viral fever'],
            recommended_specializations: ['General Medicine'],
            recommended_doctor_ids: [],
            recommended_doctors: [],
            next_steps: ['Rest', 'Hydrate'],
            follow_up_questions: [],
            emergency_message: null,
            disclaimer: 'General advice only.',
            tools_used: [],
          },
        },
      },
    });

    renderRoutes(
      [{ path: '/patient/assistant/:id', element: <AssistantView conversationId={1} /> }],
      { initialPath: '/patient/assistant/1', auth },
    );

    expect(await screen.findByText('I have had a high fever since yesterday')).toBeInTheDocument();

    const textarea = screen.getByLabelText('Describe your symptoms');
    await userEvent.type(textarea, 'What medicine should I take?');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/ai/conversations/1/messages',
        { content: 'What medicine should I take?' },
        expect.anything(),
      );
    });
  });

  it('deletes conversation when trash button is clicked', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    api.delete.mockResolvedValue({ data: null });

    renderRoutes(
      [
        { path: '/patient/assistant/:id', element: <AssistantView conversationId={1} /> },
        { path: '/patient/assistant', element: <p>Assistant landing</p> },
      ],
      { initialPath: '/patient/assistant/1', auth },
    );

    const deleteBtn = await screen.findByRole('button', { name: /Delete Fever and headache/ });
    await userEvent.click(deleteBtn);

    await waitFor(() => {
      expect(api.delete).toHaveBeenCalledWith('/ai/conversations/1');
    });
  });
});
