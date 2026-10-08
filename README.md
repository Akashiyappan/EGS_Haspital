# Onezae Health

Hospital appointment and care-coordination platform: patients book doctors, chat with them and use an
AI symptom assistant; doctors manage their day; admins manage doctors, schedules and the clinic.

* **Frontend**: React 19 + TypeScript (Vite), React Router, TanStack Query
* **Backend**: FastAPI (modular monolith), SQLAlchemy 2 (async), Alembic, **MySQL 8** (aiomysql driver)
* **Integrations**: Cloudinary (images), Groq (AI assistant, tool calling), WebSockets (realtime chat)
* No Docker required.

Design, data model, security and compliance notes: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Features

| Patient | Doctor | Admin |
|---|---|---|
| Self-registration, profile, photo | Today / upcoming / past appointments | Create, edit, (de)activate, remove doctors |
| Search doctors by name/specialization | Confirm, complete, no-show, cancel | Specializations |
| Live 30-min slot availability, booking | Patient list and details (own patients only) | Weekly schedules with multiple shifts |
| Upcoming / past appointments, cancellation | Chat with patients (text + images) | Leave, unavailability, clinic holidays |
| Chat with doctors (text + images) | Read-only schedule view | Appointments overview, users, audit log |
| AI symptom assistant with doctor suggestions | Notifications | Dashboard counters |

Cross-cutting: RBAC enforced in the API, database-level double-booking protection, appointment state
machine, realtime chat with reconnection, in-app/realtime/email notifications, reminders, audit
logging, rate limiting, structured logs with request IDs.

## Prerequisites

* Python 3.12+ and Node.js 20.19+ (22 LTS recommended)
* MySQL 8.0+ (InnoDB, utf8mb4). SQLite works as a zero-setup fallback for a quick try-out
* Optional: a Cloudinary account (image uploads) and a Groq API key (AI assistant)

## Local development

### Database (MySQL)

```sql
CREATE DATABASE onezae CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'onezae'@'localhost' IDENTIFIED BY 'choose-a-password';
GRANT ALL PRIVILEGES ON onezae.* TO 'onezae'@'localhost';
```

Then set `DATABASE_URL` in `backend/.env` (step below). For a quick try-out without MySQL, use
`DATABASE_URL=sqlite+aiosqlite:///./app.db` instead.

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                 # Windows: copy .env.example .env — set DATABASE_URL, SECRET_KEY
alembic upgrade head
python -m scripts.seed               # specializations
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Create the first administrator (admins cannot self-register):

```bash
python -m scripts.create_admin admin@example.com "Clinic" "Admin"
```

Optional demo data (admin, 4 doctors with Mon–Sat schedules, a patient; never in production):

```bash
# Windows PowerShell: $env:SEED_DEMO_PASSWORD="DemoPass1"; python -m scripts.seed --demo
SEED_DEMO_PASSWORD=DemoPass1 python -m scripts.seed --demo
# Sign in as admin.demo@example.com / patient.demo@example.com / anita.rao.demo@example.com
```

API docs: http://127.0.0.1:8000/docs (disabled when `ENVIRONMENT=production`).

### Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Vite proxies `/api` (including the WebSocket) to `127.0.0.1:8000`, so the browser sees one origin.

## Configuration

All settings are environment variables (or `backend/.env`); see `backend/.env.example` for the
full list with comments. The most important:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing key (≥32 random chars in production) |
| `DATABASE_URL` | `mysql+aiomysql://onezae:<password>@127.0.0.1:3306/onezae?charset=utf8mb4` |
| `CLINIC_TIMEZONE` | IANA zone for schedules and display (default `Asia/Kolkata`) |
| `APPOINTMENT_DURATION_MINUTES` | Slot length (default 30) |
| `CANCELLATION_CUTOFF_HOURS`, `BOOKING_WINDOW_DAYS`, `BOOKING_MIN_LEAD_MINUTES` | Booking policy |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | Image uploads (server-side only) |
| `GROQ_API_KEY`, `GROQ_MODEL` | AI assistant (server-side only) |
| `RATE_LIMIT_AUTH`, `RATE_LIMIT_AI`, `RATE_LIMIT_UPLOAD` | `requests/seconds` |
| `EMERGENCY_PHONE_NUMBER` | Shown in emergency guidance (default `112`) |

Secrets never reach the browser: the frontend only uses `VITE_*` variables (`frontend/.env.example`)
and the public `GET /api/v1/meta` endpoint.

### Enabling the AI assistant

Add your Groq key to `backend/.env` (the same provider and model as the INSURANCE-RAG backend):

```env
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
```

Restart the API, then evaluate live behaviour on the demo data:

```bash
python -m scripts.ai_eval
```

Without a key the assistant returns `503 ai_unavailable`, except for emergency symptoms, which
still receive emergency-care guidance.

### Enabling image uploads

Set the three `CLOUDINARY_*` variables. Chat images are stored as authenticated assets (signed URLs);
profile images are public. Without credentials, upload endpoints return `503 uploads_not_configured`.

## Quality checks

| | Backend (`backend/`) | Frontend (`frontend/`) |
|---|---|---|
| Lint | `ruff check .` | `npm run lint` |
| Format | `ruff format .` | `npm run format` |
| Types | `mypy app scripts` | `npm run typecheck` |
| Tests | `pytest` | `npm test` |
| Build | — | `npm run build` |

By default tests use a throw-away SQLite file per test. Run them against MySQL (recommended
before deploying; includes the concurrent-booking tests) with a dedicated empty database:

```bash
TEST_DATABASE_URL="mysql+aiomysql://onezae:<password>@127.0.0.1:3306/onezae_test?charset=utf8mb4" pytest
```

## Database migrations

```bash
alembic revision --autogenerate -m "describe change"   # after changing app/models
alembic upgrade head
alembic downgrade -1
```

Every schema change needs a migration; review autogenerated files before committing.

## Production deployment (Linux, no Docker)

nginx serves the built SPA and proxies `/api/` (REST and the `/api/v1/ws` WebSocket) to gunicorn on
`127.0.0.1:8000`.

1. **MySQL 8**: create the database and user (see `backend/.env.example`), use InnoDB with
   `utf8mb4`; enable encrypted backups (daily `mysqldump --single-transaction` or binary-log based
   point-in-time recovery) and test restores.
2. **Backend** in `/srv/onezae/backend`:
   ```bash
   python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
   cp .env.example .env   # edit: ENVIRONMENT=production, SECRET_KEY, DATABASE_URL, COOKIE_SECURE=true,
                          # CORS_ORIGINS=https://app.example.com, ALLOWED_HOSTS=app.example.com,
                          # LOG_JSON=true, FRONTEND_URL, Cloudinary, Groq
   .venv/bin/python -m scripts.seed
   .venv/bin/python -m scripts.create_admin you@hospital.org "First" "Last"
   ```
   Startup fails fast if production settings are unsafe (default secret, DEBUG, insecure cookies,
   wildcard CORS).
3. **Run the API**: apply migrations with `alembic upgrade head` on each release, then run
   `gunicorn app.main:app -c gunicorn.conf.py` under a process manager of your choice. Realtime
   pushes are per worker process: use `WEB_CONCURRENCY=1`, or add a Redis broker, see
   `gunicorn.conf.py`. Schedule `python -m scripts.send_reminders` every 5–15 minutes (cron or similar).
4. **Frontend**: `npm ci && npm run build`, publish `frontend/dist/` to `/srv/onezae/frontend/dist`.
5. **Reverse proxy** (e.g. nginx) with TLS: serve `frontend/dist` with an SPA fallback to `index.html`,
   proxy `/api/` to `127.0.0.1:8000`, and forward WebSocket upgrade headers for `/api/v1/ws`.

**Windows server**: gunicorn doesn't run on Windows; use
`uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers` under a service manager (NSSM)
behind IIS or nginx.
