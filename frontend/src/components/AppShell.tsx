import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router';

import { appointmentKeys } from '@/features/appointments/api';
import { useAuth } from '@/features/auth/useAuth';
import { chatKeys, useChatUnread } from '@/features/chat/api';
import { notificationKeys } from '@/features/notifications/api';
import { useMeta, useRealtimeEvent, useRealtimeState } from '@/lib/hooks';
import type { Role } from '@/lib/types';

import { Icon, type IconName } from './Icon';
import { NotificationBell } from './NotificationBell';
import { Avatar } from './ui';
import { ToastProvider } from './ToastProvider';

interface NavItem {
  to: string;
  label: string;
  icon: IconName;
  end?: boolean;
  badge?: 'chat';
}

const NAV: Record<Role, NavItem[]> = {
  PATIENT: [
    { to: '/patient', label: 'Dashboard', icon: 'home', end: true },
    { to: '/patient/doctors', label: 'Find a doctor', icon: 'stethoscope' },
    { to: '/patient/appointments', label: 'Appointments', icon: 'calendar' },
    { to: '/patient/prescriptions', label: 'Prescriptions', icon: 'pill' },
    { to: '/patient/records', label: 'Health records', icon: 'list' },
    { to: '/patient/messages', label: 'Messages', icon: 'chat', badge: 'chat' },
    { to: '/patient/assistant', label: 'AI assistant', icon: 'sparkles' },
    { to: '/patient/profile', label: 'Profile', icon: 'user' },
  ],
  DOCTOR: [
    { to: '/doctor', label: 'Dashboard', icon: 'home', end: true },
    { to: '/doctor/appointments', label: 'Appointments', icon: 'calendar' },
    { to: '/doctor/prescriptions', label: 'Prescriptions', icon: 'pill' },
    { to: '/doctor/patients', label: 'Patients', icon: 'users' },
    { to: '/doctor/messages', label: 'Messages', icon: 'chat', badge: 'chat' },
    { to: '/doctor/schedule', label: 'Schedule', icon: 'clock' },
    { to: '/doctor/profile', label: 'Profile', icon: 'user' },
  ],
  ADMIN: [
    { to: '/admin', label: 'Dashboard', icon: 'home', end: true },
    { to: '/admin/doctors', label: 'Doctors', icon: 'stethoscope' },
    { to: '/admin/appointments', label: 'Appointments', icon: 'calendar' },
    { to: '/admin/specializations', label: 'Specializations', icon: 'tag' },
    { to: '/admin/holidays', label: 'Clinic holidays', icon: 'clock' },
    { to: '/admin/users', label: 'Users', icon: 'users' },
    { to: '/admin/audit', label: 'Activity history', icon: 'shield' },
  ],
};

/** Keeps cached data fresh from realtime events (REST stays the source of truth). */
function RealtimeSync() {
  const queryClient = useQueryClient();
  useRealtimeEvent(['notification.created'], () => {
    void queryClient.invalidateQueries({ queryKey: notificationKeys.all });
    void queryClient.invalidateQueries({ queryKey: appointmentKeys.all });
  });
  useRealtimeEvent(['message.created', 'conversation.read', 'presence'], () => {
    void queryClient.invalidateQueries({ queryKey: chatKeys.conversations });
    void queryClient.invalidateQueries({ queryKey: chatKeys.unread });
  });
  useRealtimeEvent(['reconnected'], () => {
    void queryClient.invalidateQueries();
  });
  return null;
}

function ChatBadge() {
  const { data } = useChatUnread();
  if (!data?.unread) return null;
  return <span className="nav-badge">{data.unread > 99 ? '99+' : data.unread}</span>;
}

export function AppShell() {
  const { user, logout } = useAuth();
  const meta = useMeta();
  const connection = useRealtimeState();
  const [menuOpen, setMenuOpen] = useState(false);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    const saved = window.localStorage.getItem('egs-theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    window.localStorage.setItem('egs-theme', theme);
  }, [theme]);

  if (!user) return null;
  const items = NAV[user.role];

  return (
    <div className={menuOpen ? 'shell menu-open' : 'shell'}>
      <RealtimeSync />
      <aside className="sidebar" aria-label="Main navigation">
        <Link to="/" className="brand" onClick={() => setMenuOpen(false)}>
          <span className="brand-mark">
            <Icon name="shield" size={18} />
          </span>
          {meta.app_name.replace(/ API$/, '')}
        </Link>
        <nav>
          {items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
              onClick={() => setMenuOpen(false)}
            >
              <Icon name={item.icon} />
              <span>{item.label}</span>
              {item.badge === 'chat' && <ChatBadge />}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button
            type="button"
            className="theme-toggle"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            onClick={() => setTheme((current) => (current === 'dark' ? 'light' : 'dark'))}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={18} />
            <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
          </button>
          <span className="role-pill">{user.role.toLowerCase()}</span>
        </div>
      </aside>
      <button
        type="button"
        className="scrim"
        aria-label="Close menu"
        tabIndex={-1}
        onClick={() => setMenuOpen(false)}
      />
      <div className="shell-main">
        <ToastProvider />
        <header className="topbar">
          <button
            type="button"
            className="ghost icon-button menu-toggle"
            aria-label="Open menu"
            onClick={() => setMenuOpen(true)}
          >
            <Icon name="menu" />
          </button>
          <div className="topbar-spacer" />
          {connection === 'closed' && (
            <span className="badge badge-warning" role="status">
              Reconnecting…
            </span>
          )}
          <NotificationBell />
          <div className="row user-chip">
            <Avatar name={user.full_name} url={user.avatar_url} size={32} />
            <span className="hide-sm">
              {user.role === 'DOCTOR' ? `Dr. ${user.full_name}` : user.full_name}
            </span>
          </div>
          <button
            type="button"
            className="ghost icon-button"
            aria-label="Sign out"
            title="Sign out"
            onClick={() => void logout()}
          >
            <Icon name="logout" />
          </button>
        </header>
        <main className="content" id="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
