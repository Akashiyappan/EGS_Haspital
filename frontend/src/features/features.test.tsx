import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { validatePeriods } from '@/features/admin/schedule';
import type { Appointment } from '@/lib/types';
import { apiError, makeAuth, makeUser, renderPage } from '@/test/utils';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  api,
  tokenStore: { get: () => 'token', set: vi.fn() },
  refreshAccessToken: vi.fn().mockResolvedValue('token'),
  setUnauthorizedHandler: vi.fn(),
}));

vi.mock('@/lib/realtime', () => ({
  realtime: {
    subscribe: () => () => undefined,
    onStateChange: () => () => undefined,
    send: vi.fn(),
    state: 'open',
  },
}));

const { BookingPanel } = await import('@/features/doctors/BookingPanel');
const { AppointmentList } = await import('@/features/appointments/AppointmentList');
const { AssistantResult } = await import('@/features/ai/AssistantView');
const { ChatView } = await import('@/features/chat/ChatView');
const { DoctorForm } = await import('@/features/admin/DoctorForm');

const ok = <T,>(data: T) => Promise.resolve({ data });

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
});

// --- Booking -----------------------------------------------------------------

describe('BookingPanel', () => {
  const slots = [
    { starts_at: '2030-01-08T02:30:00Z', ends_at: '2030-01-08T03:00:00Z', available: false },
    { starts_at: '2030-01-08T03:00:00Z', ends_at: '2030-01-08T03:30:00Z', available: true },
  ];

  beforeEach(() => {
    api.get.mockImplementation((url: string) => {
      if (url.endsWith('/availability')) {
        return ok({
          doctor_id: 7,
          timezone: 'Asia/Kolkata',
          days: [
            { date: '2030-01-07', available_slots: 0 },
            { date: '2030-01-08', available_slots: 1 },
          ],
        });
      }
      return ok({ doctor_id: 7, date: '2030-01-08', timezone: 'Asia/Kolkata', slots });
    });
  });

  it('shows clinic-time slots and disables taken ones', async () => {
    renderPage(<BookingPanel doctorId={7} onBooked={vi.fn()} />);
    const taken = await screen.findByRole('button', { name: /8:00/ });
    const free = screen.getByRole('button', { name: /8:30/ });
    expect(taken).toBeDisabled();
    expect(free).toBeEnabled();
    // The fully booked day cannot be selected.
    expect(screen.getByRole('option', { name: /Full/ })).toBeDisabled();
  });

  it('books the selected slot', async () => {
    const onBooked = vi.fn();
    api.post.mockReturnValue(ok({ id: 99 }));
    renderPage(<BookingPanel doctorId={7} onBooked={onBooked} />);
    await userEvent.click(await screen.findByRole('button', { name: /8:30/ }));
    await userEvent.type(screen.getByLabelText(/Reason for visit/), 'Check-up');
    await userEvent.click(screen.getByRole('button', { name: 'Confirm booking' }));
    expect(api.post).toHaveBeenCalledWith('/appointments', {
      doctor_id: 7,
      starts_at: '2030-01-08T03:00:00Z',
      reason: 'Check-up',
    });
    await waitFor(() => expect(onBooked).toHaveBeenCalled());
  });

  it('explains a lost race and refreshes the slots', async () => {
    api.post.mockRejectedValue(
      apiError(409, 'slot_unavailable', 'This slot is no longer available'),
    );
    renderPage(<BookingPanel doctorId={7} onBooked={vi.fn()} />);
    await userEvent.click(await screen.findByRole('button', { name: /8:30/ }));
    const slotCalls = () =>
      api.get.mock.calls.filter(([url]) => String(url).endsWith('/slots')).length;
    const before = slotCalls();
    await userEvent.click(screen.getByRole('button', { name: 'Confirm booking' }));
    await waitFor(() => expect(slotCalls()).toBeGreaterThan(before));
    expect(screen.queryByRole('button', { name: 'Confirm booking' })).not.toBeInTheDocument();
  });
});

// --- Appointments ------------------------------------------------------------

function appointment(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: 5,
    starts_at: '2030-01-08T03:00:00Z',
    ends_at: '2030-01-08T03:30:00Z',
    status: 'BOOKED',
    reason: 'Headache',
    doctor_notes: null,
    cancellation_reason: null,
    cancelled_at: null,
    created_at: '2030-01-01T00:00:00Z',
    doctor: { id: 2, full_name: 'Vikram Shah', avatar_url: null, specializations: ['Cardiology'] },
    patient: { id: 3, full_name: 'Priya Kumar', avatar_url: null },
    allowed_actions: ['cancel'],
    ...overrides,
  };
}

describe('AppointmentList', () => {
  it('only offers the actions the server allows', () => {
    renderPage(
      <AppointmentList
        appointments={[appointment({ allowed_actions: ['confirm', 'cancel'] })]}
        perspective="doctor"
      />,
    );
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Mark completed' })).not.toBeInTheDocument();
  });

  it('shows no actions for terminal appointments', () => {
    renderPage(
      <AppointmentList
        appointments={[appointment({ status: 'COMPLETED', allowed_actions: [] })]}
        perspective="patient"
      />,
    );
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('cancels with a reason', async () => {
    api.post.mockReturnValue(ok(appointment({ status: 'CANCELLED', allowed_actions: [] })));
    renderPage(<AppointmentList appointments={[appointment()]} perspective="patient" />);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText(/Reason/), 'Feeling better');
    await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel appointment' }));
    expect(api.post).toHaveBeenCalledWith('/appointments/5/cancel', { reason: 'Feeling better' });
  });

  it('shows the cancellation policy error', async () => {
    api.post.mockRejectedValue(
      apiError(
        400,
        'cancellation_window_closed',
        'Appointments can only be cancelled up to 2 hours before they start',
      ),
    );
    renderPage(<AppointmentList appointments={[appointment()]} perspective="patient" />);
    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await userEvent.click(
      within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel appointment' }),
    );
    expect(await screen.findByText(/only be cancelled up to 2 hours/)).toBeInTheDocument();
  });
});

// --- AI assistant ------------------------------------------------------------

describe('AssistantResult', () => {
  const base = {
    summary: 'These symptoms can have several causes.',
    urgency: 'routine' as const,
    possible_concerns: ['Viral infection'],
    recommended_specializations: ['General Medicine'],
    recommended_doctor_ids: [4],
    next_steps: ['Rest and drink fluids'],
    follow_up_questions: ['How high is the fever?'],
    emergency_message: null,
    disclaimer: 'This assistant provides general health information only.',
    tools_used: ['search_doctors_by_specialization'],
    recommended_doctors: [
      {
        id: 4,
        first_name: 'Anita',
        last_name: 'Rao',
        full_name: 'Anita Rao',
        avatar_url: null,
        qualification: 'MBBS',
        experience_years: 12,
        bio: null,
        specializations: [{ id: 1, name: 'General Medicine', description: null, is_active: true }],
      },
    ],
  };

  it('renders guidance, verified doctors and the disclaimer', () => {
    renderPage(<AssistantResult result={base} />);
    expect(screen.getByText('Routine')).toBeInTheDocument();
    expect(screen.getByText('Viral infection')).toBeInTheDocument();
    expect(screen.getByText('Dr. Anita Rao')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View & book' })).toHaveAttribute(
      'href',
      '/patient/doctors/4',
    );
    expect(screen.getByText(/general health information only/)).toBeInTheDocument();
  });

  it('shows an emergency banner for emergencies', () => {
    renderPage(
      <AssistantResult
        result={{
          ...base,
          urgency: 'emergency',
          emergency_message: 'Call emergency services (112) now.',
        }}
      />,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Call emergency services (112) now.');
  });
});

// --- Chat --------------------------------------------------------------------

describe('ChatView', () => {
  const conversation = {
    id: 11,
    counterpart: {
      user_id: 2,
      doctor_id: 2,
      patient_id: null,
      full_name: 'Vikram Shah',
      avatar_url: null,
      role: 'DOCTOR',
      online: true,
    },
    last_message: null,
    last_message_at: null,
    unread_count: 0,
  };

  beforeEach(() => {
    api.get.mockImplementation((url: string) => {
      if (url === '/chat/conversations') {
        return ok({ items: [conversation], total: 1, page: 1, page_size: 50, pages: 1 });
      }
      return ok({
        items: [
          {
            id: 1,
            conversation_id: 11,
            sender_id: 2,
            message_type: 'TEXT',
            body: 'How are you feeling today?',
            client_id: null,
            attachments: [],
            created_at: '2030-01-08T03:00:00Z',
          },
        ],
        has_more: false,
      });
    });
    api.post.mockImplementation((url: string, body: { body?: string; client_id?: string }) => {
      if (url.endsWith('/read')) return ok(null);
      return ok({
        id: 2,
        conversation_id: 11,
        sender_id: 1,
        message_type: 'TEXT',
        body: body.body,
        client_id: body.client_id,
        attachments: [],
        created_at: '2030-01-08T03:05:00Z',
      });
    });
  });

  it('shows history, marks it read and sends messages', async () => {
    const auth = makeAuth({ status: 'authenticated', user: makeUser('PATIENT') });
    renderPage(<ChatView basePath="/patient/messages" conversationId={11} />, { auth });

    expect(await screen.findByText('How are you feeling today?')).toBeInTheDocument();
    expect(screen.getByText('Online')).toBeInTheDocument();
    await waitFor(() =>
      expect(api.post).toHaveBeenCalledWith('/chat/conversations/11/read', { message_id: 1 }),
    );

    await userEvent.type(screen.getByLabelText('Message'), 'Much better, thanks');
    await userEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Much better, thanks')).toBeInTheDocument();
    const sendCall = api.post.mock.calls.find(([url]) => url === '/chat/conversations/11/messages');
    expect(sendCall?.[1]).toMatchObject({ body: 'Much better, thanks' });
    expect(sendCall?.[1].client_id).toBeTruthy(); // idempotency key for safe retries
  });

  it('shows the empty state without conversations', async () => {
    api.get.mockReturnValue(ok({ items: [], total: 0, page: 1, page_size: 50, pages: 0 }));
    renderPage(<ChatView basePath="/patient/messages" conversationId={null} />, {
      auth: makeAuth({ status: 'authenticated', user: makeUser('PATIENT') }),
    });
    expect(await screen.findByText('No conversations yet')).toBeInTheDocument();
  });
});

// --- Admin ------------------------------------------------------------------

describe('DoctorForm', () => {
  beforeEach(() => {
    api.get.mockReturnValue(
      ok([
        { id: 1, name: 'Cardiology', description: null, is_active: true },
        { id: 2, name: 'Neurology', description: null, is_active: true },
      ]),
    );
  });

  it('requires a specialization and a strong temporary password', async () => {
    renderPage(<DoctorForm onSaved={vi.fn()} />);
    await screen.findByText('Cardiology');
    await userEvent.type(screen.getByLabelText('First name'), 'Grace');
    await userEvent.type(screen.getByLabelText('Email'), 'grace@example.com');
    await userEvent.type(screen.getByLabelText('Temporary password'), 'short');
    await userEvent.click(screen.getByRole('button', { name: 'Create doctor' }));
    expect(screen.getByText('Choose at least one specialization')).toBeInTheDocument();
    expect(screen.getByText('Use at least 8 characters')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('creates a doctor', async () => {
    const onSaved = vi.fn();
    api.post.mockReturnValue(ok({ id: 9 }));
    renderPage(<DoctorForm onSaved={onSaved} />);
    await userEvent.click(await screen.findByLabelText('Cardiology'));
    await userEvent.type(screen.getByLabelText('First name'), 'Grace');
    await userEvent.type(screen.getByLabelText('Email'), 'grace@example.com');
    await userEvent.type(screen.getByLabelText('Temporary password'), 'TempPass1');
    await userEvent.click(screen.getByRole('button', { name: 'Create doctor' }));
    expect(api.post).toHaveBeenCalledWith(
      '/admin/doctors',
      expect.objectContaining({
        first_name: 'Grace',
        email: 'grace@example.com',
        temporary_password: 'TempPass1',
        specialization_ids: [1],
      }),
    );
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});

describe('schedule validation', () => {
  const period = (weekday: number, start: string, end: string) => ({
    key: `${weekday}${start}`,
    weekday,
    start_time: start,
    end_time: end,
    effective_from: '',
    effective_until: '',
  });

  it('accepts multiple non-overlapping shifts', () => {
    expect(
      validatePeriods([period(0, '08:00', '10:00'), period(0, '14:00', '16:00')], 30),
    ).toBeNull();
  });

  it('rejects overlaps and too-short periods', () => {
    expect(validatePeriods([period(0, '08:00', '10:00'), period(0, '09:30', '11:00')], 30)).toMatch(
      /overlap/,
    );
    expect(validatePeriods([period(1, '08:00', '08:15')], 30)).toMatch(/at least 30 minutes/);
  });
});
