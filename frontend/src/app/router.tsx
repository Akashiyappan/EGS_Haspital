import type { ComponentType } from 'react';
import { createBrowserRouter, type RouteObject } from 'react-router';

import { AppShell } from '@/components/AppShell';
import { RouteError } from '@/components/RouteError';
import { FullPageSpinner } from '@/components/Spinner';
import { GuestRoute, HomeRedirect, RoleRoute, SignedInRoute } from '@/features/auth/guards';

type Module = Record<string, unknown>;

// Pages are code-split per area; each import becomes its own chunk.
function lazyPage<M extends Module>(load: () => Promise<M>, name: keyof M & string) {
  return async () => ({ Component: (await load())[name] as ComponentType });
}

const patient = () => import('@/features/patient/pages');
const doctor = () => import('@/features/doctor/pages');
const admin = () => import('@/features/admin/pages');
const passwords = () => import('@/pages/PasswordPages');

const page = (load: () => Promise<{ default: ComponentType }>) => lazyPage(load, 'default');

const routes: RouteObject[] = [
  {
    errorElement: <RouteError />,
    hydrateFallbackElement: <FullPageSpinner />,
    children: [
      { index: true, element: <HomeRedirect /> },
      {
        element: <GuestRoute />,
        children: [
          { path: '/login', lazy: page(() => import('@/pages/LoginPage')) },
          { path: '/staff/login', lazy: page(() => import('@/pages/StaffLoginPage')) },
          { path: '/register', lazy: page(() => import('@/pages/RegisterPage')) },
          { path: '/forgot-password', lazy: lazyPage(passwords, 'ForgotPasswordPage') },
        ],
      },
      { path: '/reset-password', lazy: lazyPage(passwords, 'ResetPasswordPage') },
      {
        element: <SignedInRoute />,
        children: [{ path: '/change-password', lazy: lazyPage(passwords, 'ChangePasswordPage') }],
      },
      {
        path: '/patient',
        element: <RoleRoute roles={['PATIENT']} />,
        children: [
          {
            element: <AppShell />,
            children: [
              { index: true, lazy: lazyPage(patient, 'PatientDashboard') },
              { path: 'doctors', lazy: lazyPage(patient, 'FindDoctorsPage') },
              { path: 'doctors/:doctorId', lazy: lazyPage(patient, 'DoctorProfilePage') },
              { path: 'appointments', lazy: lazyPage(patient, 'PatientAppointmentsPage') },
              { path: 'records', lazy: lazyPage(patient, 'PatientRecordsPage') },
              { path: 'messages/:conversationId?', lazy: lazyPage(patient, 'PatientMessagesPage') },
              { path: 'assistant/:conversationId?', lazy: lazyPage(patient, 'AssistantPage') },
              { path: 'profile', lazy: page(() => import('@/pages/ProfilePage')) },
            ],
          },
        ],
      },
      {
        path: '/doctor',
        element: <RoleRoute roles={['DOCTOR']} />,
        children: [
          {
            element: <AppShell />,
            children: [
              { index: true, lazy: lazyPage(doctor, 'DoctorDashboard') },
              { path: 'appointments', lazy: lazyPage(doctor, 'DoctorAppointmentsPage') },
              { path: 'patients', lazy: lazyPage(doctor, 'DoctorPatientsPage') },
              { path: 'patients/:patientId', lazy: lazyPage(doctor, 'DoctorPatientDetailPage') },
              { path: 'messages/:conversationId?', lazy: lazyPage(doctor, 'DoctorMessagesPage') },
              { path: 'schedule', lazy: lazyPage(doctor, 'DoctorSchedulePage') },
              { path: 'profile', lazy: lazyPage(doctor, 'DoctorProfilePage') },
            ],
          },
        ],
      },
      {
        path: '/admin',
        element: <RoleRoute roles={['ADMIN']} />,
        children: [
          {
            element: <AppShell />,
            children: [
              { index: true, lazy: lazyPage(admin, 'AdminDashboard') },
              { path: 'doctors', lazy: lazyPage(admin, 'AdminDoctorsPage') },
              { path: 'doctors/new', lazy: lazyPage(admin, 'AdminNewDoctorPage') },
              { path: 'doctors/:doctorId', lazy: lazyPage(admin, 'AdminDoctorDetailPage') },
              { path: 'appointments', lazy: lazyPage(admin, 'AdminAppointmentsPage') },
              { path: 'specializations', lazy: lazyPage(admin, 'AdminSpecializationsPage') },
              { path: 'users', lazy: lazyPage(admin, 'AdminUsersPage') },
              { path: 'holidays', lazy: lazyPage(admin, 'AdminHolidaysPage') },
              { path: 'audit', lazy: lazyPage(admin, 'AdminAuditPage') },
              { path: 'profile', lazy: page(() => import('@/pages/ProfilePage')) },
            ],
          },
        ],
      },
      { path: '*', lazy: page(() => import('@/pages/NotFoundPage')) },
    ],
  },
];

export const router = createBrowserRouter(routes);
