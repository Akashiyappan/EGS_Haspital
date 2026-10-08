import { useEffect, useRef, useState } from 'react';

import {
  useMarkNotificationsRead,
  useNotifications,
  useUnreadNotifications,
} from '@/features/notifications/api';
import { formatRelative } from '@/lib/time';

import { Icon } from './Icon';
import { EmptyState, QueryState } from './ui';

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const unread = useUnreadNotifications();
  const list = useNotifications();
  const markRead = useMarkNotificationsRead();
  const count = unread.data?.unread ?? 0;

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="popover-anchor" ref={containerRef}>
      <button
        type="button"
        className="ghost icon-button"
        aria-label={count ? `Notifications (${count} unread)` : 'Notifications'}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="bell" />
        {count > 0 && <span className="dot-count">{count > 99 ? '99+' : count}</span>}
      </button>
      {open && (
        <div className="popover" role="dialog" aria-label="Notifications">
          <div className="row space-between popover-header">
            <strong>Notifications</strong>
            {count > 0 && (
              <button type="button" className="link-button" onClick={() => markRead.mutate('all')}>
                Mark all read
              </button>
            )}
          </div>
          <QueryState
            isLoading={list.isLoading}
            error={list.error}
            isEmpty={!list.data?.items.length}
            empty={<EmptyState icon="bell" title="You're all caught up" />}
          >
            <ul className="notification-list">
              {list.data?.items.map((n) => (
                <li key={n.id} className={n.read_at ? '' : 'unread'}>
                  <button
                    type="button"
                    className="notification-item"
                    onClick={() => !n.read_at && markRead.mutate(n.id)}
                  >
                    <span className="notification-title">{n.title}</span>
                    <span className="small-text">{n.body}</span>
                    <span className="muted small-text">{formatRelative(n.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </QueryState>
        </div>
      )}
    </div>
  );
}
