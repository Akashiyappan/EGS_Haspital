@echo off
setlocal
cd /d "%~dp0backend"

echo Activating virtual environment...
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [ERROR] .venv not found. Run run_backend.bat first or run 'python -m venv .venv'.
    pause
    exit /b 1
)

echo Seeding default users (Admin, Doctor, Patient)...
python -m scripts.seed_defaults

pause
