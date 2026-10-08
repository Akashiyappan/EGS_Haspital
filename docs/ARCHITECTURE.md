# Onezae Health — Architecture

Hospitalization / doctor-appointment platform: **React (Vite, TypeScript)** web client and a
**FastAPI** modular monolith on **MySQL 8** (InnoDB, utf8mb4; SQLite only as a zero-setup fallback), with
**Cloudinary** for images and **Groq** for the AI symptom assistant. No Docker required.

## 1. Roles and portals

| Role    | How the account is created         | Sign-in                         | Area       |
|---------|------------------------------------|---------------------------------|------------|
| PATIENT | Public self-registration            | `/login` (`portal=patient`)     | `/patient` |
| DOCTOR  | Created by an admin (temp password)| `/staff/login` (`portal=staff`) | `/doctor`  |
| ADMIN   | `python -m scripts.create_admin`   | `/staff/login` (`portal=staff`) | `/admin`   |

The login endpoint rejects a user on the wrong portal with the same error as a wrong password, so
roles cannot be probed. Admin-issued temporary passwords set `must_change_password`; until it is
cleared, every endpoint except `/auth/change-password`, `/users/me` and logout returns
`403 password_change_required`.

## 2. Backend layout

```
app/
  api/deps.py            authentication + RBAC dependencies (CurrentUser, AdminUser, CurrentDoctor,
                         CurrentPatient, user_rate_limit)
  api/v1/routes/         thin HTTP layer: auth, users, doctors, appointments, chat, notifications,
                         ai, doctor_portal, admin, meta, health, ws (WebSocket)
  services/              business rules and transactions
    auth_service         login per portal, tokens, password change/reset
    doctor_service       admin doctor management (create/update/activate/soft-delete/reset)
    schedule_service     weekly rules, time off, conflict detection
    slot_service         slot generation (pure function + DB loader), bookability check
    appointment_service  booking, state machine, role rules, reminders
    chat_service         conversations, messages, read receipts, realtime fan-out
    notification_service Notifier (in-app + realtime + email channels, dedupe)
    audit_service        append-only audit records
  ai/                    assistant: llm.py, agent.py, tools/, prompts/, safety.py, service.py
  integrations/          storage.py (Cloudinary), email.py (provider abstraction)
  realtime/manager.py    WebSocket connection registry
  models/                SQLAlchemy models; enums.py holds the appointment state machine
  core/                  config, security, errors, logging, middleware, rate limiting, time helpers
```

Routes validate input (Pydantic), resolve the caller (dependencies) and delegate to a service.
Authorization is always enforced server-side: role checks in dependencies, ownership checks in
services (resources a caller may not see return **404**, not 403, to avoid confirming existence).

## 3. Data model

```
users ─┬─ patients ──┬─ appointments ─┬─ doctors ─┬─ doctor_specializations ─ specializations
       │             │                │           ├─ doctor_schedules   (weekly rules, clinic time)
       │             │                │           └─ doctor_time_off    (doctor_id NULL = clinic-wide)
       │             ├─ conversations ┴─ messages ─ message_attachments (Cloudinary metadata)
       │             └─ ai_conversations ─ ai_messages
       ├─ notifications (unique user_id + dedupe_key)
       └─ audit_logs
```

* Role-specific data lives in `doctors` / `patients` keyed by `user_id`; identity and credentials
  only in `users`.
* Every instant is stored in UTC as `DATETIME(6)` (MySQL has no timezone-aware type; the
  `UTCDateTime` column type converts on write and re-attaches UTC on read). Schedule rules store
  clinic wall-clock times.
* Soft deletion for users (`deleted_at`, `is_active`); clinical history is never hard-deleted.
* Integer primary keys (consistent with the existing schema). Enumeration is mitigated by
  per-resource authorization; UUIDs can be introduced later if public IDs are needed.

### Double-booking protection

MySQL has no partial indexes, so a stored generated column marks the slot an appointment holds,
and unique indexes on it enforce the rule in the database under any concurrency:

```sql
active_slot_starts_at DATETIME(6) GENERATED ALWAYS AS
  (CASE WHEN status IN ('BOOKED', 'CONFIRMED') THEN starts_at ELSE NULL END) STORED,

CREATE UNIQUE INDEX uq_appointments_doctor_active_slot  ON appointments (doctor_id,  active_slot_starts_at);
CREATE UNIQUE INDEX uq_appointments_patient_active_slot ON appointments (patient_id, active_slot_starts_at);
```

Cancelled or finished appointments have `NULL` there, and a unique index allows any number of
`NULL`s. Connections use `READ COMMITTED` (no gap locks); if InnoDB resolves a race as a deadlock
or lock-wait timeout instead of a duplicate key, that is also reported as `409 slot_unavailable`.

Booking first runs a friendly availability check (`slot_service.assert_bookable`), then inserts;
a duplicate-key error from a lost race becomes `409 slot_unavailable`. Cancelled appointments leave
the index, so a freed slot can be rebooked. Tests cover five concurrent bookers (one 201, four 409)
and the case where the application check is bypassed entirely.

### Appointment state machine

```
BOOKED ──confirm──▶ CONFIRMED ──complete──▶ COMPLETED
   │                   ├──no_show──▶ NO_SHOW
   └──cancel──┐        └──cancel──┐
              ▼                   ▼
          CANCELLED           CANCELLED
```

Role rules on top: patients may only cancel, and only up to `CANCELLATION_CUTOFF_HOURS` before the
start; doctors/admins may complete or mark no-show only after the start. Each appointment response
includes `allowed_actions`, computed by the same function the backend enforces, so the UI never
re-implements the rules.

### Scheduling and time zones

* `doctor_schedules`: weekday + start/end (clinic wall-clock) + `slot_minutes` (default
  `APPOINTMENT_DURATION_MINUTES` = 30) + optional `effective_from/until`. Several rows per weekday
  model multiple shifts; date ranges model temporary or seasonal schedules. Overlaps are rejected.
* `doctor_time_off`: leave, holidays, unavailability; `doctor_id NULL` blocks every doctor.
* Slots are generated per date by converting wall-clock to UTC with `zoneinfo`; times that do not
  exist (DST spring-forward) are skipped and ambiguous ones resolve to the first occurrence. Only
  whole slots inside a working period are produced; nothing outside working hours.
* Changing a schedule or adding time off never silently cancels appointments; the API returns
  `conflicting_appointment_ids` for the admin to handle.

## 4. Authentication

* bcrypt password hashing; passwords need 8+ characters with a letter and a digit (≤72 bytes).
* Access token: JWT (15 min) with `sub`, `role` (informational), `ver`. Role and status are always
  re-read from the database.
* Refresh token: httpOnly, `SameSite=Lax`, path-scoped cookie, rotated on every refresh.
* `token_version` on the user: bumped by logout, password change/reset, deactivation and admin
  password reset, which revokes every outstanding token at once.
* Password reset: single-use JWT (invalidated by the version bump), link uses a URL fragment so the
  token is not sent to servers or written to access logs; responses never reveal whether an email
  exists.

## 5. Chat and realtime

* Messages are written to the database first, then pushed over WebSocket (`/api/v1/ws`).
* WebSocket authentication is the first frame (`{"type":"auth","token":...}`), never a URL query
  parameter. The socket closes with `4401` when the access token expires; the client refreshes and
  reconnects with backoff, then re-syncs with `GET .../messages?after_id=` (the database is the
  source of truth, so nothing is lost while offline).
* Idempotent sends via `client_id` (unique per conversation and sender).
* Chat requires a care relationship (at least one appointment between the doctor and patient).
  Admins cannot read conversations.
* Unread counts use per-side `last_read_message_id`; one "new message" notification per unread
  streak, without message content.
* Images: content-sniffed (JPEG/PNG/WebP), size-limited, uploaded to Cloudinary as
  `authenticated` assets; only the signed delivery URL and metadata are stored. If the database
  write fails the uploaded asset is deleted.

## 6. AI assistant (agentic tool use)

```
React ─▶ POST /ai/conversations/{id}/messages ─▶ ai.service.exchange
          ─▶ SymptomAgent (bounded loop) ─▶ ToolRegistry ─▶ tools ─▶ domain services ─▶ DB
          ─▶ safety.enforce ─▶ persisted ─▶ response (doctors hydrated from DB)
```

* Provider: Groq chat completions with tool calling (`GROQ_MODEL`, default `openai/gpt-oss-120b`,
  as in the reference INSURANCE-RAG backend), behind `LLMClient` so it can be swapped or faked.
* Tools (read-only, Pydantic-validated arguments): `list_specializations`,
  `search_doctors_by_specialization`, `get_doctor_profile`, `get_doctor_availability`,
  `get_available_appointment_slots`. They call domain services, never SQL, and return only public
  doctor data. Unknown tools and invalid arguments are returned to the model as errors.
* Budgets: `AI_MAX_ITERATIONS`, `AI_MAX_TOKENS`, `AI_TIMEOUT_SECONDS`; when exhausted, a final
  answer is requested with tools disabled; malformed output gets one repair attempt.
* "Agentic RAG" here means retrieval through tools over live hospital data (specializations,
  doctors, availability). A document knowledge base (e.g. vetted patient-education content) can be
  added later as another tool without changing the agent.

Safety rules enforced in code (`ai/safety.py`), independent of model behaviour:

1. Red-flag symptoms (chest pain, breathing difficulty, loss of consciousness, severe bleeding,
   stroke signs, self-harm …) force `urgency=emergency` and a fixed emergency message, even when
   the model or provider fails.
2. Recommended doctors are filtered to IDs a tool returned in that run; doctor details are loaded
   from the database at read time, so invented doctors cannot appear.
3. Specializations are normalized to existing ones; unknown names are dropped.
4. Items containing medication dosing are removed; the disclaimer is fixed text.
5. Prompt-injection phrases are refused without calling the model.
6. Patient text is never logged (only lengths, tool names, urgency, timings).

The system prompt (`ai/prompts/symptom_assistant.py`) is versioned; the version and model are
stored with each assistant message.

## 7. Notifications and audit

`Notifier` stages notifications inside the business transaction and delivers them after commit
through channels: in-app (database, the source of truth), realtime (WebSocket) and email (selected
types, via the `EmailSender` abstraction; the console backend only logs metadata). SMS or push can
be added as further channels. Duplicates are prevented by `(user_id, dedupe_key)`. Reminders run
from `scripts/send_reminders.py` on a timer and are idempotent.

Audit log entries are written for authentication events, doctor lifecycle, schedule and time-off
changes, specialization changes, user activation, bookings and appointment status changes. Details
never contain passwords, tokens or clinical free text.

## 8. Frontend

```
src/
  app/            router (lazy, per-area chunks), providers
  components/     shell, icons, form fields, states (loading/error/empty), modal, tabs, pagination
  features/
    auth/         AuthProvider (in-memory access token, cookie refresh), guards, login form
    admin/        doctors, schedule editor, time off, specializations, users, audit
    doctor/       dashboard, appointments, patients, schedule, profile
    patient/      dashboard, doctor search, booking, appointments, messages, assistant
    appointments/ list + actions driven by allowed_actions
    chat/         conversations, thread (optimistic sends, retries, catch-up after reconnect)
    ai/           assistant view and structured result rendering
  lib/            api client, realtime client, time zone helpers, validation, hooks
```

All times are displayed in the clinic time zone from `GET /meta`, so patients and staff in
different zones see the same schedule.

## 9. Requirement review (section 42)

| Item | Status |
|------|--------|
| Forgot / reset / change password | Implemented (email via provider abstraction) |
| Email verification | Deferred — needs a real email provider; flag + token flow can reuse the reset pattern |
| Account activation / deactivation | Implemented (doctors via doctor endpoints, others via users) |
| Session / token expiry | Implemented (15-min access, rotating 7-day refresh, version revocation) |
| Doctor leave, holidays, unavailable periods | Implemented (`doctor_time_off`, clinic-wide entries) |
| Temporary / recurring schedules, multiple shifts | Implemented |
| Cancellation policy | Implemented (`CANCELLATION_CUTOFF_HOURS`) |
| Rescheduling | Deferred — today: cancel + rebook; a single transactional endpoint is a next step |
| Reminders | Implemented (timer-driven, idempotent) |
| Notification system | Implemented (in-app, realtime, email abstraction) |
| Unread chat counts, message pagination | Implemented |
| Upload limits / type validation | Implemented (content sniffing, size limit) |
| Availability conflicts | Implemented (overlap validation, conflict reporting) |
| Concurrent booking | Implemented and tested (DB constraint) |
| Audit logs | Implemented |
| API and AI rate limiting | Implemented (in-process; see limitations) |
| Error monitoring | Structured JSON logs with request IDs; Sentry/OpenTelemetry is a next step |
| Indexes and constraints | Implemented (FKs, checks, generated-column unique indexes, query indexes) |
| Soft deletion | Implemented for users/doctors |
| Backup / recovery | Operational: see README (mysqldump / binlog PITR guidance) |

## 10. Known limitations

* **Realtime across workers**: the WebSocket registry is per process. With several gunicorn
  workers, pushes reach only sockets on the same worker (clients still catch up via REST). Run one
  worker for realtime or add a Redis pub/sub broker behind `realtime/manager.py`.
* **Rate limits are per process** (same reason); use a shared backend for strict global limits.
* **Cloudinary signed URLs do not expire** on the standard plan; anyone holding a URL can view the
  image. Strict expiry needs Cloudinary token-based authentication or proxying images through the
  API.
* Email delivery is a console stub until a provider is configured.
* The AI assistant was verified with a scripted model in automated tests; run
  `python -m scripts.ai_eval` with a real `GROQ_API_KEY` to evaluate live model behaviour.

## 11. Privacy and compliance notes

The system follows privacy-by-design (least-privilege access, minimum-necessary data, audit
trail, no PHI in logs, encrypted transport assumed via TLS), but **no regulatory compliance is
claimed**. Before handling real patient data, review at least:

* Applicable law (e.g. India's DPDP Act 2023, HIPAA if serving US patients, GDPR for EU residents):
  consent capture, purpose limitation, data subject access/erasure, breach notification.
* Data processing agreements with Cloudinary and Groq; Groq processes patient-described symptoms,
  so confirm its data-retention terms and region, or disable the assistant.
* Encryption at rest for MySQL (InnoDB tablespace encryption) and backups; key management; backup retention and restore
  drills.
* Retention schedule for messages, AI conversations and audit logs.
* Clinical safety review of the assistant's prompt, red-flag list and emergency number per region.
