@echo off
setlocal
cd /d "%~dp0backend"

echo ========================================================
echo       EGS Hospital - Backend Setup and Runner
echo ========================================================

REM 1. Check or Create Virtual Environment
if not exist ".venv\Scripts\activate.bat" (
    echo [1/5] Creating Python virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Ensure Python 3.12+ is installed.
        pause
        exit /b 1
    )
) else (
    echo [1/5] Virtual environment (.venv) found.
)

REM 2. Activate Virtual Environment
echo [2/5] Activating virtual environment...
call .venv\Scripts\activate.bat

REM 3. Install Requirements
echo [3/5] Installing backend dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

REM 4. Ensure Database Exists, Run Migrations & Seeder
echo [4/5] Checking database and applying migrations...
python -m scripts.init_db
if errorlevel 1 (
    echo [WARNING] Database initialization failed. Check your MySQL server status and DATABASE_URL credentials.
    pause
    exit /b 1
)

alembic upgrade head
if errorlevel 1 (
    echo [WARNING] Database migration failed.
    echo Please check your DATABASE_URL in backend\.env (verify MySQL username/password or switch to SQLite).
    pause
    exit /b 1
)


echo Seeding default users (Admin, Doctor, Patient)...
python -m scripts.seed_defaults

REM 5. Start Uvicorn Server
echo [5/5] Starting backend API at http://127.0.0.1:8000 ...
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

pause
