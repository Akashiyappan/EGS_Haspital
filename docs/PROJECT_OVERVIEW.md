# Onezae Health — Project Overview

This document is the shared reference for the purpose, current implementation, integrations, and maintenance of Onezae Health. Update it when the product, architecture, providers, or deployment process changes. For deeper design decisions, see [Architecture](ARCHITECTURE.md); for setup commands, see the root [README](../README.md).

## What the project is

Onezae Health is a web based hospital and clinic appointment and care coordination platform. It gives patients a way to find doctors, book and manage appointments, communicate with care providers, review prescriptions and records, and get initial symptom guidance. Doctors manage appointments and patient communication. Administrators manage doctors, schedules, users, and clinic operations.

The product has three role based portals:

| Role | Main responsibilities |
| --- | --- |
| Patient | Register and manage a profile; find doctors and availability; book or cancel appointments; chat with doctors; view prescriptions and records; use the symptom assistant. |
| Doctor | View a schedule and assigned patients; manage appointment status; chat with patients; create and manage prescriptions; update professional profile information. |
| Admin | Manage doctors, specializations, users, schedules, clinic closures and holidays; review appointments, dashboard information, and audit history. |

Core capabilities include appointment availability and booking, cancellation and appointment status rules, structured e-prescriptions, patient records, realtime chat and notifications, email notification hooks, doctor scheduling and time off, audit logging, and an AI symptom assistant that can look up the real doctor directory and appointment availability.

## Technology stack

| Area | Technology in the repository |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, React Router, TanStack Query, Axios |
| Backend | Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2 async |
| API | JSON REST API under `/api/v1`; WebSocket endpoint for realtime chat/events |
| Database | MySQL 8 / InnoDB / `utf8mb4` is the intended primary database; SQLite is supported for local quick starts and automated tests |
| Schema changes | Alembic migrations |
| Authentication | JWT access tokens, rotating refresh token in an httpOnly cookie, bcrypt password hashing, role and resource authorization |
| Frontend checks | TypeScript, ESLint, Prettier, Vitest and Testing Library |
| Backend checks | Ruff, mypy, pytest |

The backend is organized as a modular monolith: API routes handle HTTP concerns, service modules implement business rules, SQLAlchemy models represent persisted data, and integrations are isolated behind service abstractions.

## AI provider and behavior

- **Provider:** Groq, called by the backend through the Groq Python SDK and its chat completions API.
- **Configured model:** `openai/gpt-oss-120b` (`GROQ_MODEL` in backend configuration). This is the model identifier sent to Groq; it does not mean the application calls the OpenAI API.
- **Purpose:** Provide informational symptom guidance and, when useful, search live hospital data for specializations, doctors, profiles, and bookable appointment slots. Patients can book a selected slot from the assistant flow.
- **How it works:** A bounded tool-calling agent uses validated backend tools. Tools call application services rather than querying the database directly. Doctor recommendations are restricted to doctors returned by those tools. Conversations and assistant results are persisted.
- **Safety:** The assistant is not a diagnostic service. Backend checks can identify configured emergency red flags and force emergency guidance, constrain recommendations to known doctors/specialties, remove unsupported medication doses, and attach a fixed disclaimer. Do not present it as a substitute for clinical care.
- **Configuration:** Set `GROQ_API_KEY` on the backend. The browser never calls Groq and must never contain this key. Without a key, general model based guidance is unavailable; some directory/availability retrieval and emergency fallback behavior can still work.

AI behavior, model identifiers, prompts, tools, and safety rules can change. Keep this section synchronized with `backend/app/ai/`, `backend/app/api/v1/routes/ai.py`, and backend settings.

## Cloud services and external providers

| Service | Current use | Configuration / status |
| --- | --- | --- |
| Groq | Hosted AI inference for the symptom assistant | Optional; backend `GROQ_API_KEY` and `GROQ_MODEL`. |
| Cloudinary | Cloud image storage and delivery for profile photos and chat attachments | Optional; backend `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET`. Chat assets use authenticated delivery; profile images use public delivery. |
| Email | Notification and password reset delivery abstraction | No live email vendor is configured in this repository. Current backends are `console` (development logging) and `disabled`; production email requires implementing/configuring a provider. |
| Application hosting | Not identified in source/configuration | The README describes a possible Linux deployment using nginx and Gunicorn, or Uvicorn behind IIS/nginx on Windows. This is deployment guidance, not evidence of a chosen hosting cloud. |
| Database hosting | Not identified in source/configuration | MySQL is configured by `DATABASE_URL`; the repository does not specify a managed database provider. |

Do not claim AWS, Azure, Google Cloud, or another hosting provider unless deployment configuration is added to the project and confirmed. Cloudinary is the current image cloud service; Groq is the current hosted AI provider.

## Main application architecture

```text
Browser (React / TypeScript)
  ├── REST requests and refresh-cookie authentication
  └── WebSocket connection for realtime updates
            ↓
FastAPI API (/api/v1)
  ├── authentication, validation, rate limits, role checks
  ├── services: scheduling, appointments, chat, prescriptions, users, notifications
  ├── AI agent → Groq + validated tools → application services
  └── SQLAlchemy async session
            ↓
MySQL (primary) / SQLite (local and tests)

Backend image integration → Cloudinary (optional)
Backend email abstraction → console/disabled today
```

The API is the authority for permissions and business rules. The frontend provides the role specific user experience, but must not be relied on to enforce access control. Realtime connections are managed in process; the current deployment notes recommend one backend worker unless a cross-worker broker is added.

## Important domain and security rules

- Appointment slot duration, booking window, minimum lead time, cancellation cutoff, reminder lead time, and clinic timezone are configurable. The current example timezone is `Asia/Kolkata` and the example appointment duration is 30 minutes.
- MySQL generated columns and unique indexes protect against simultaneous double booking. Preserve the database level protection when modifying appointment persistence.
- Appointment states and permitted actions are enforced by backend services. Keep UI action availability aligned with the API response and server rules.
- Authorization is enforced server side by role and resource ownership. Patient/doctor data should be disclosed only for the permitted relationship and purpose.
- Access tokens are kept in browser memory; refresh tokens are httpOnly cookies. Never put secrets in `VITE_*` variables, frontend source, or committed `.env` files.
- Images are content-validated and size-limited by the backend. Chat image delivery is restricted via signed/authenticated URLs.
- Production configuration validates important security settings such as a strong secret, secure cookies, disabled debug mode, and non-wildcard CORS.
- This application handles sensitive health and identity data. Before real clinical or production use, the operator must assess applicable privacy, security, retention, consent, incident response, and regulatory obligations for its jurisdiction. The presence of security controls in code does not itself establish compliance or certification.

## Data areas

The persistent model includes users and role profiles (patients/doctors), doctor specializations and schedules, time off, appointments, prescriptions and medicines, patient records, doctor-patient conversations and messages/attachments, AI conversations and messages, notifications, and audit logs. UTC instants are used for persisted event times; clinic schedules use local wall-clock time interpreted in the configured clinic timezone. See the architecture document and `backend/app/models/` for the detailed schema.

## Repository map

```text
backend/
  app/api/           Versioned FastAPI routes and dependencies
  app/services/      Business rules and transaction workflows
  app/models/        SQLAlchemy persistence models and enums
  app/schemas/       Pydantic API request/response schemas
  app/ai/            Groq client, agent, prompts, tools, safety and orchestration
  app/integrations/  Cloudinary storage and email abstraction
  app/core/          Configuration, security, middleware, logging and utilities
  alembic/           Database migrations
  scripts/           Database setup, seeding, reminders and AI evaluation
  tests/             Backend automated tests
frontend/
  src/app/           Application shell and route setup
  src/features/      Patient, doctor, admin and product feature modules
  src/components/    Shared interface components
  src/lib/           API client, types, validation, time and realtime helpers
docs/
  ARCHITECTURE.md    Detailed architecture and design notes
  PROJECT_OVERVIEW.md This product and technology reference
```

## Configuration and running

Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to `frontend/.env.local`, then configure the local database and any optional providers. Backend secrets belong only in backend environment configuration. Frontend `VITE_*` variables are public and are baked into the browser build.

The documented local setup uses Python 3.12+, Node.js 20.19+ (or newer supported version), and MySQL 8; SQLite can be used for a quick local run. The Windows runner scripts are provided at the repository root. For the exact setup and run commands, default local accounts, migration workflow, and deployment example, follow [README.md](../README.md). Do not use development credentials or default secrets in a deployed environment.

## Guidance for future changes

1. Keep domain rules in backend services and validate inputs with Pydantic schemas. Keep route handlers thin and enforce authorization in API dependencies/services.
2. For schema changes, update SQLAlchemy models and add/review an Alembic migration. Never rely on a development database auto-create as a production migration strategy.
3. Preserve transaction boundaries and database constraints for booking, prescription, and other sensitive workflows.
4. Add or update tests for behavior changes, especially role access, ownership, appointment concurrency, time zones, AI fallbacks, and safety rules.
5. Keep provider calls behind backend integrations/abstractions. Document provider name, purpose, environment variables, data sent, fallback behavior, and operational requirements when adding a service.
6. Review privacy and security effects before logging, storing, or sending patient data to a new provider. Keep credentials out of source control and client-side bundles.
7. Update this document, `README.md`, and `docs/ARCHITECTURE.md` when features, providers, supported runtimes, or deployment practices materially change.

## Current known limitations / items to decide

- No production hosting, managed database, or cloud deployment provider is selected in repository configuration.
- No production email transport is implemented; `console` and `disabled` are the only configured backends.
- Realtime fan-out is process local; multi-worker deployments need a shared broker or a single worker.
- AI responses are informational and depend on an external provider when model generation is enabled. Provider availability, retention, and data processing terms should be reviewed before sending real patient information.
- Confirm that product claims, privacy notices, clinical workflow, and regulatory requirements match the actual deployment and jurisdiction before launch.
