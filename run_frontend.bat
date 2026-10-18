@echo off
setlocal
cd /d "%~dp0frontend"

echo ========================================================
echo       EGS Hospital - Frontend Setup and Runner
echo ========================================================

REM 1. Install dependencies if node_modules does not exist
if not exist "node_modules" (
    echo [1/2] Installing frontend dependencies (npm install)...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Failed to install npm dependencies. Ensure Node.js 20+ is installed.
        pause
        exit /b 1
    )
) else (
    echo [1/2] Node modules already installed.
)

REM 2. Start Vite Dev Server
echo [2/2] Starting Vite Dev Server at http://localhost:5173 ...
call npm run dev

pause
