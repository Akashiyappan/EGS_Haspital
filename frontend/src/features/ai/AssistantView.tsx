import { type FormEvent, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { Icon } from '@/components/Icon';
import { Alert, EmptyState, QueryState } from '@/components/ui';
import { DoctorCard } from '@/features/doctors/DoctorCard';
import { getErrorMessage } from '@/lib/errors';
import { useMeta } from '@/lib/hooks';
import { formatRelative } from '@/lib/time';

import {
  type AIMessage,
  type AIResult,
  type Urgency,
  useAIConversations,
  useAIMessages,
  useAskAssistant,
  useCreateAIConversation,
  useDeleteAIConversation,
} from './api';

const URGENCY: Record<Urgency, { label: string; tone: string; text: string }> = {
  emergency: {
    label: 'Emergency',
    tone: 'emergency',
    text: 'Seek emergency care immediately.',
  },
  urgent: { label: 'Urgent', tone: 'urgent', text: 'See a doctor within 24 hours.' },
  routine: { label: 'Routine', tone: 'routine', text: 'Book a regular appointment.' },
  self_care: {
    label: 'Self-care',
    tone: 'selfcare',
    text: 'Monitor your symptoms; see a doctor if they worsen or persist.',
  },
};

const EXAMPLES = [
  'I have had a fever and headache for two days',
  'Dry cough and sore throat since yesterday',
  'Stomach pain after meals for a week',
];

export function AssistantResult({ result }: { result: AIResult }) {
  const urgency = URGENCY[result.urgency];
  return (
    <div className="stack ai-result">
      {result.emergency_message ? (
        <div className="emergency-banner" role="alert">
          <Icon name="alert" />
          <div>
            <strong>Possible emergency</strong>
            <p>{result.emergency_message}</p>
          </div>
        </div>
      ) : (
        <div className={`urgency urgency-${urgency.tone}`}>
          <strong>{urgency.label}</strong> · {urgency.text}
        </div>
      )}
      <p>{result.summary}</p>
      {result.possible_concerns.length > 0 && (
        <div>
          <h4>Possible areas of concern</h4>
          <ul>
            {result.possible_concerns.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {result.next_steps.length > 0 && (
        <div>
          <h4>Suggested next steps</h4>
          <ul>
            {result.next_steps.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {result.follow_up_questions.length > 0 && (
        <div>
          <h4>A doctor may ask</h4>
          <ul>
            {result.follow_up_questions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}
      {result.recommended_specializations.length > 0 && (
        <div className="chips">
          {result.recommended_specializations.map((name) => (
            <span key={name} className="chip">
              {name}
            </span>
          ))}
        </div>
      )}
      {result.recommended_doctors.length > 0 && (
        <div className="stack">
          <h4>Doctors at this hospital who can help</h4>
          <div className="card-grid">
            {result.recommended_doctors.map((doctor) => (
              <DoctorCard
                key={doctor.id}
                doctor={doctor}
                actions={
                  <Link className="button small" to={`/patient/doctors/${doctor.id}`}>
                    View & book
                  </Link>
                }
              />
            ))}
          </div>
        </div>
      )}
      <p className="disclaimer">
        <Icon name="shield" size={16} /> {result.disclaimer}
      </p>
    </div>
  );
}

function MessageBubble({ message }: { message: AIMessage }) {
  if (message.role === 'USER') {
    return (
      <div className="bubble mine">
        <p>{message.content}</p>
      </div>
    );
  }
  return (
    <div className="ai-message">
      <span className="ai-avatar" aria-hidden>
        <Icon name="sparkles" size={18} />
      </span>
      {message.result ? <AssistantResult result={message.result} /> : <p>{message.content}</p>}
    </div>
  );
}

export function AssistantView({ conversationId }: { conversationId: number | null }) {
  const meta = useMeta();
  const navigate = useNavigate();
  const conversations = useAIConversations();
  const create = useCreateAIConversation();
  const remove = useDeleteAIConversation();

  async function startNew() {
    const conversation = await create.mutateAsync();
    void navigate(`/patient/assistant/${conversation.id}`);
  }

  return (
    <div className={conversationId ? 'chat-layout thread-open' : 'chat-layout'}>
      <aside className="chat-sidebar">
        <div className="chat-sidebar-header">
          <button
            type="button"
            className="small"
            onClick={() => void startNew()}
            disabled={create.isPending}
          >
            <Icon name="plus" size={16} /> New consultation
          </button>
        </div>
        <QueryState
          isLoading={conversations.isLoading}
          error={conversations.error}
          isEmpty={!conversations.data?.items.length}
          empty={<p className="muted small-text pad">No consultations yet.</p>}
        >
          <ul className="conversation-list">
            {conversations.data?.items.map((c) => (
              <li key={c.id} className="row">
                <Link
                  to={`/patient/assistant/${c.id}`}
                  className={c.id === conversationId ? 'conversation active' : 'conversation'}
                >
                  <span className="conversation-text">
                    <span className="strong clamp-1">{c.title}</span>
                    <span className="muted small-text">{formatRelative(c.updated_at)}</span>
                  </span>
                </Link>
                <button
                  type="button"
                  className="ghost icon-button"
                  aria-label={`Delete ${c.title}`}
                  onClick={() =>
                    remove.mutate(c.id, {
                      onSuccess: () => {
                        if (c.id === conversationId) void navigate('/patient/assistant');
                      },
                    })
                  }
                >
                  <Icon name="trash" size={16} />
                </button>
              </li>
            ))}
          </ul>
        </QueryState>
      </aside>
      <section className="chat-thread">
        {!meta.ai_enabled && (
          <Alert tone="warning">
            The AI assistant is not configured on this server. Emergency symptoms still receive
            emergency guidance.
          </Alert>
        )}
        {conversationId ? (
          <AssistantThread key={conversationId} conversationId={conversationId} />
        ) : (
          <EmptyState
            icon="sparkles"
            title="Describe your symptoms"
            description="Get general guidance and find the right kind of doctor. This is not a diagnosis."
            action={
              <button type="button" onClick={() => void startNew()}>
                Start a consultation
              </button>
            }
          />
        )}
      </section>
    </div>
  );
}

function AssistantThread({ conversationId }: { conversationId: number }) {
  const messages = useAIMessages(conversationId);
  const ask = useAskAssistant(conversationId);
  const [text, setText] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages.data?.length, ask.isPending]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const content = text.trim();
    if (content.length < 2 || ask.isPending) return;
    ask.mutate(content, { onSuccess: () => setText('') });
  }

  return (
    <>
      <div className="messages">
        <QueryState isLoading={messages.isLoading} error={messages.error}>
          {messages.data?.length === 0 && (
            <div className="stack pad">
              <p className="muted">
                Describe what you feel, how long it has lasted and how severe it is.
              </p>
              <div className="chips">
                {EXAMPLES.map((example) => (
                  <button
                    key={example}
                    type="button"
                    className="chip chip-button"
                    onClick={() => setText(example)}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.data?.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </QueryState>
        {ask.isPending && (
          <div className="ai-message">
            <span className="ai-avatar" aria-hidden>
              <Icon name="sparkles" size={18} />
            </span>
            <p className="muted">Reviewing your symptoms and checking our doctors…</p>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      {ask.isError && <Alert>{getErrorMessage(ask.error)}</Alert>}
      <form className="composer" onSubmit={submit}>
        <textarea
          className="composer-input"
          aria-label="Describe your symptoms"
          placeholder="e.g. I have had a high fever and a severe headache for two days"
          rows={2}
          maxLength={2000}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) submit(event);
          }}
        />
        <button
          type="submit"
          className="icon-button"
          aria-label="Send"
          disabled={ask.isPending || text.trim().length < 2}
        >
          <Icon name="send" />
        </button>
      </form>
    </>
  );
}
