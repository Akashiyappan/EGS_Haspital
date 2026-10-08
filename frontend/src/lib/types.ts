export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type Role = 'ADMIN' | 'DOCTOR' | 'PATIENT';

export interface Meta {
  app_name: string;
  clinic_timezone: string;
  appointment_duration_minutes: number;
  cancellation_cutoff_hours: number;
  booking_window_days: number;
  upload_max_bytes: number;
  upload_allowed_types: string[];
  uploads_enabled: boolean;
  ai_enabled: boolean;
}

export interface Specialization {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
}

export interface DoctorPublic {
  id: number;
  first_name: string;
  last_name: string | null;
  full_name: string;
  avatar_url: string | null;
  qualification: string | null;
  experience_years: number;
  bio: string | null;
  specializations: Specialization[];
}

export interface DoctorAdmin extends DoctorPublic {
  user_id: number;
  email: string;
  phone: string | null;
  is_active: boolean;
  must_change_password: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface Slot {
  starts_at: string;
  ends_at: string;
  available: boolean;
}

export interface DaySlots {
  doctor_id: number;
  date: string;
  timezone: string;
  slots: Slot[];
}

export interface Availability {
  doctor_id: number;
  timezone: string;
  days: { date: string; available_slots: number }[];
}

export type AppointmentStatus = 'BOOKED' | 'CONFIRMED' | 'CANCELLED' | 'COMPLETED' | 'NO_SHOW';
export type AppointmentAction = 'confirm' | 'cancel' | 'complete' | 'no_show';

export interface Appointment {
  id: number;
  starts_at: string;
  ends_at: string;
  status: AppointmentStatus;
  reason: string | null;
  doctor_notes: string | null;
  cancellation_reason: string | null;
  cancelled_at: string | null;
  created_at: string;
  doctor: { id: number; full_name: string; avatar_url: string | null; specializations: string[] };
  patient: { id: number; full_name: string; avatar_url: string | null };
  allowed_actions: AppointmentAction[];
}

export interface ScheduleRule {
  id?: number;
  weekday: number;
  start_time: string;
  end_time: string;
  slot_minutes?: number | null;
  effective_from?: string | null;
  effective_until?: string | null;
}

export type TimeOffKind = 'LEAVE' | 'HOLIDAY' | 'UNAVAILABLE';

export interface TimeOff {
  id: number;
  doctor_id: number | null;
  kind: TimeOffKind;
  starts_at: string;
  ends_at: string;
  reason: string | null;
}

export interface Notification {
  id: number;
  type: string;
  title: string;
  body: string;
  data: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}
