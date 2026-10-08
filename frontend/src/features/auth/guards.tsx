import { Navigate, Outlet, useLocation } from 'react-router';

import { FullPageSpinner } from '@/components/Spinner';
import type { Role } from '@/lib/types';

import { HOME_BY_ROLE } from './roles';
import { useAuth } from './useAuth';

/**
 * Client-side role routing. This is a UX convenience only: every API call is
 * authorized by the backend independently.
 */
export function RoleRoute({ roles }: { roles: Role[] }) {
  const { status, user } = useAuth();
  const location = useLocation();
  const staffArea = roles.every((role) => role !== 'PATIENT');

  if (status === 'loading' || (status === 'authenticated' && !user)) {
    return <FullPageSpinner />;
  }
  if (status === 'unauthenticated' || !user) {
    return (
      <Navigate to={staffArea ? '/staff/login' : '/login'} replace state={{ from: location }} />
    );
  }
  if (user.must_change_password) {
    return <Navigate to="/change-password" replace />;
  }
  if (!roles.includes(user.role)) {
    return <Navigate to={HOME_BY_ROLE[user.role]} replace />;
  }
  return <Outlet />;
}

/** For login/register pages: signed-in users are sent to their home. */
export function GuestRoute() {
  const { status, user } = useAuth();
  if (status === 'loading') return <FullPageSpinner />;
  if (status === 'authenticated' && user) {
    return (
      <Navigate
        to={user.must_change_password ? '/change-password' : HOME_BY_ROLE[user.role]}
        replace
      />
    );
  }
  return <Outlet />;
}

/** Any signed-in user, including one who must still change a temporary password. */
export function SignedInRoute() {
  const { status } = useAuth();
  if (status === 'loading') return <FullPageSpinner />;
  if (status === 'unauthenticated') return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function HomeRedirect() {
  const { status, user } = useAuth();
  if (status === 'loading' || (status === 'authenticated' && !user)) return <FullPageSpinner />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  return <Navigate to={HOME_BY_ROLE[user.role]} replace />;
}
