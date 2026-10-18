import { useQueryClient } from '@tanstack/react-query';
import { type FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router';

import { Icon } from '@/components/Icon';
import { Alert, Avatar, EmptyState, QueryState } from '@/components/ui';
import { useAuth } from '@/features/auth/useAuth';
import { getErrorMessage } from '@/lib/errors';
import { useClinicTimezone, useMeta, useRealtimeEvent } from '@/lib/hooks';
import { realtime } from '@/lib/realtime';
import { formatRelative, formatTime } from '@/lib/time';

import {
  type ChatMessage,
  type Conversation,
  chatApi,
  chatKeys,
  newClientId,
  useConversations,
} from './api';

type PendingMessage = ChatMessage & { pending?: boolean; failed?: boolean; file?: File };

function mergeMessages(current: PendingMessage[], incoming: ChatMessage[]): PendingMessage[] {
  const byKey = new Map<string, PendingMessage>();
  for (const message of current) byKey.set(message.client_id ?? `id:${message.id}`, message);
  for (const message of incoming) {
    // A confirmed message replaces its optimistic copy (matched by client_id).
    byKey.set(message.client_id ?? `id:${message.id}`, message);
  }
  return [...byKey.values()].sort((a, b) => {
    if (a.pending !== b.pending) return a.pending ? 1 : -1;
    return a.id - b.id;
  });
}

/** Conversation list + thread, shared by the doctor and patient portals. */
export function ChatView({
  basePath,
  conversationId,
}: {
  basePath: string;
  conversationId: number | null;
}) {
  const conversations = useConversations();
  const { user } = useAuth();
  const active = conversations.data?.items.find((c) => c.id === conversationId) ?? null;
  const isDoctor = user?.role === 'DOCTOR';
  const directoryPath = isDoctor ? '/doctor/patients' : '/patient/doctors';

  return (
    <div className={conversationId ? 'chat-layout thread-open' : 'chat-layout'}>
      <aside className="chat-sidebar">
        <div className="chat-sidebar-header">
          <Link className="button small" to={directoryPath}>
            <Icon name="plus" size={16} /> {isDoctor ? 'Find a patient' : 'Find a doctor'}
          </Link>
          <p className="muted small-text">Chats open after an appointment is booked.</p>
        </div>
        <QueryState
          isLoading={conversations.isLoading}
          error={conversations.error}
          isEmpty={!conversations.data?.items.length}
          empty={
            <EmptyState
              icon="chat"
              title="No conversations yet"
              description={
                isDoctor
                  ? 'A patient can chat with you after you have an appointment together.'
                  : 'Book an appointment with a doctor to start a private chat about your care.'
              }
            />
          }
        >
          <ul className="conversation-list">
            {conversations.data?.items.map((c) => (
              <li key={c.id}>
                <Link
                  to={`${basePath}/${c.id}`}
                  className={c.id === conversationId ? 'conversation active' : 'conversation'}
                >
                  <span className="avatar-wrap">
                    <Avatar name={c.counterpart.full_name} url={c.counterpart.avatar_url} />
                    {c.counterpart.online && <span className="online-dot" title="Online" />}
                  </span>
                  <span className="conversation-text">
                    <span className="strong">
                      {c.counterpart.role === 'DOCTOR' ? 'Dr. ' : ''}
                      {c.counterpart.full_name}
                    </span>
                    <span className="muted small-text clamp-1">
                      {c.last_message
                        ? c.last_message.message_type === 'IMAGE'
                          ? '📷 Photo'
                          : c.last_message.body
                        : 'No messages yet'}
                    </span>
                  </span>
                  <span className="conversation-meta">
                    {c.last_message_at && (
                      <span className="muted small-text">{formatRelative(c.last_message_at)}</span>
                    )}
                    {c.unread_count > 0 && <span className="nav-badge">{c.unread_count}</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </QueryState>
      </aside>
      <section className="chat-thread">
        {active ? (
          <Thread key={active.id} conversation={active} basePath={basePath} />
        ) : (
          <EmptyState icon="chat" title="Select a conversation" />
        )}
      </section>
    </div>
  );
}

function Thread({ conversation, basePath }: { conversation: Conversation; basePath: string }) {
  const { user } = useAuth();
  const meta = useMeta();
  const timeZone = useClinicTimezone();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [messages, setMessages] = useState<PendingMessage[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [text, setText] = useState('');
  const [typing, setTyping] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastTypingSent = useRef(0);
  const conversationId = conversation.id;

  const latestId = messages.filter((m) => !m.pending).at(-1)?.id;

  const markRead = useCallback(
    (messageId: number | undefined) => {
      if (!messageId) return;
      void chatApi.markRead(conversationId, messageId).then(() => {
        void queryClient.invalidateQueries({ queryKey: chatKeys.conversations });
        void queryClient.invalidateQueries({ queryKey: chatKeys.unread });
      });
    },
    [conversationId, queryClient],
  );

  // Initial page.
  useEffect(() => {
    let cancelled = false;
    chatApi
      .messages(conversationId, {})
      .then((page) => {
        if (cancelled) return;
        setMessages(page.items);
        setHasMore(page.has_more);
        markRead(page.items.at(-1)?.id);
      })
      .catch((err: unknown) => !cancelled && setError(err))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [conversationId, markRead]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages.length]);

  const catchUp = useCallback(() => {
    if (!latestId) return;
    void chatApi.messages(conversationId, { after_id: latestId }).then((page) => {
      setMessages((current) => mergeMessages(current, page.items));
      markRead(page.items.at(-1)?.id);
    });
  }, [conversationId, latestId, markRead]);

  useRealtimeEvent(['message.created'], (event) => {
    const message = event.data as ChatMessage;
    if (message.conversation_id !== conversationId) return;
    setMessages((current) => mergeMessages(current, [message]));
    if (message.sender_id !== user?.id) {
      setTyping(false);
      markRead(message.id);
    }
  });
  useRealtimeEvent(['typing'], (event) => {
    const data = event.data as { conversation_id: number };
    if (data.conversation_id !== conversationId) return;
    setTyping(true);
  });
  // Re-sync anything missed while disconnected.
  useRealtimeEvent(['reconnected'], catchUp);

  useEffect(() => {
    if (!typing) return;
    const timer = setTimeout(() => setTyping(false), 4000);
    return () => clearTimeout(timer);
  }, [typing]);

  async function loadOlder() {
    const oldest = messages.find((m) => !m.pending)?.id;
    if (!oldest) return;
    const page = await chatApi.messages(conversationId, { before_id: oldest });
    setMessages((current) => mergeMessages(current, page.items));
    setHasMore(page.has_more);
  }

  async function deliver(pending: PendingMessage) {
    try {
      const saved = pending.file
        ? await chatApi.sendImage(
            conversationId,
            pending.file,
            pending.body ?? '',
            pending.client_id!,
          )
        : await chatApi.sendText(conversationId, pending.body ?? '', pending.client_id!);
      setMessages((current) => mergeMessages(current, [saved]));
      void queryClient.invalidateQueries({ queryKey: chatKeys.conversations });
    } catch (err) {
      setError(err);
      setMessages((current) =>
        current.map((m) => (m.client_id === pending.client_id ? { ...m, failed: true } : m)),
      );
    }
  }

  function enqueue(body: string, file?: File) {
    if (!user) return;
    const pending: PendingMessage = {
      id: Number.MAX_SAFE_INTEGER,
      conversation_id: conversationId,
      sender_id: user.id,
      message_type: file ? 'IMAGE' : 'TEXT',
      body: body || null,
      client_id: newClientId(),
      attachments: [],
      created_at: new Date().toISOString(),
      pending: true,
      file,
    };
    setError(null);
    setMessages((current) => [...current, pending]);
    void deliver(pending);
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    const body = text.trim();
    if (!body) return;
    setText('');
    enqueue(body);
  }

  function onFile(file: File | undefined) {
    if (!file) return;
    if (!meta.upload_allowed_types.includes(file.type)) {
      setError(new Error('Only JPEG, PNG or WebP images can be sent.'));
      return;
    }
    if (file.size > meta.upload_max_bytes) {
      setError(
        new Error(
          `Images must be ${Math.round(meta.upload_max_bytes / 1024 / 1024)} MB or smaller.`,
        ),
      );
      return;
    }
    enqueue(text.trim(), file);
    setText('');
  }

  function onType(value: string) {
    setText(value);
    const now = Date.now();
    if (now - lastTypingSent.current > 3000) {
      lastTypingSent.current = now;
      realtime.send('typing', { conversation_id: conversationId });
    }
  }

  const { counterpart } = conversation;
  return (
    <>
      <header className="thread-header">
        <button
          type="button"
          className="ghost icon-button back-button"
          aria-label="Back to conversations"
          onClick={() => void navigate(basePath)}
        >
          <Icon name="chevronLeft" />
        </button>
        <Avatar name={counterpart.full_name} url={counterpart.avatar_url} />
        <div>
          <div className="strong">
            {counterpart.role === 'DOCTOR' ? 'Dr. ' : ''}
            {counterpart.full_name}
          </div>
          <div className="muted small-text">
            {typing ? 'typing…' : counterpart.online ? 'Online' : 'Offline'}
          </div>
        </div>
      </header>
      <div className="messages" aria-live="polite">
        {loading && <p className="muted">Loading messages…</p>}
        {hasMore && (
          <button type="button" className="link-button center" onClick={() => void loadOlder()}>
            Load earlier messages
          </button>
        )}
        {messages.map((message) => {
          const mine = message.sender_id === user?.id;
          return (
            <div
              key={message.client_id ?? message.id}
              className={`bubble ${mine ? 'mine' : 'theirs'}${message.pending ? ' pending' : ''}`}
            >
              {message.attachments.map((a) => (
                <a key={a.id} href={a.url} target="_blank" rel="noreferrer noopener">
                  <img
                    src={a.url}
                    alt="Shared attachment"
                    className="bubble-image"
                    loading="lazy"
                  />
                </a>
              ))}
              {message.pending && message.file && (
                <span className="small-text muted">Uploading image…</span>
              )}
              {message.body && <p>{message.body}</p>}
              <span className="bubble-meta">
                {message.failed
                  ? 'Not sent'
                  : message.pending
                    ? 'Sending…'
                    : formatTime(message.created_at, timeZone)}
              </span>
              {message.failed && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setMessages((current) =>
                      current.map((m) =>
                        m.client_id === message.client_id ? { ...m, failed: false } : m,
                      ),
                    );
                    void deliver(message);
                  }}
                >
                  Retry
                </button>
              )}
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
      {error ? <Alert>{getErrorMessage(error)}</Alert> : null}
      <form className="composer" onSubmit={onSubmit}>
        <input
          ref={fileInput}
          type="file"
          accept={meta.upload_allowed_types.join(',')}
          hidden
          onChange={(event) => {
            onFile(event.target.files?.[0]);
            event.target.value = '';
          }}
        />
        <button
          type="button"
          className="ghost icon-button"
          aria-label="Attach image"
          title={meta.uploads_enabled ? 'Attach image' : 'Image uploads are not configured'}
          disabled={!meta.uploads_enabled}
          onClick={() => fileInput.current?.click()}
        >
          <Icon name="image" />
        </button>
        <input
          className="composer-input"
          placeholder="Write a message"
          aria-label="Message"
          value={text}
          maxLength={4000}
          onChange={(event) => onType(event.target.value)}
        />
        <button type="submit" className="icon-button" aria-label="Send" disabled={!text.trim()}>
          <Icon name="send" />
        </button>
      </form>
    </>
  );
}
