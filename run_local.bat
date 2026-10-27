@echo off
setlocal
cd /d "%~dp0"

title AI Company Phase 2

echo ========================================================
echo             AI COMPANY PHASE 2
echo ========================================================
echo.

REM ========================================================
REM STEP 1 - Check Python
REM ========================================================

echo [1/6] Checking Python...

where python >nul 2>&1

if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not available in PATH.
    echo Install Python 3.11 or later and try again.
    echo.
    pause
    exit /b 1
)

python --version

REM ========================================================
REM STEP 2 - Create virtual environment if missing
REM ========================================================

echo.
echo [2/6] Checking virtual environment...

if not exist ".venv\Scripts\python.exe" (

    echo Virtual environment not found.
    echo Creating .venv...
    echo.

    python -m venv .venv

    if errorlevel 1 (
        echo.
        echo ERROR: Unable to create virtual environment.
        pause
        exit /b 1
    )

    echo Virtual environment created successfully.

) else (

    echo Virtual environment already exists.

)

REM ========================================================
REM STEP 3 - Upgrade pip on first setup
REM ========================================================

echo.
echo [3/6] Checking project dependencies...

if not exist ".venv\.setup_complete" (

    echo First-time setup detected.
    echo.
    echo Upgrading pip...

    ".venv\Scripts\python.exe" -m pip install --upgrade pip

    if errorlevel 1 (
        echo.
        echo ERROR: pip upgrade failed.
        pause
        exit /b 1
    )

    REM ====================================================
    REM STEP 4 - Install requirements
    REM ====================================================

    echo.
    echo [4/6] Installing AI Company dependencies...
    echo This may take a few minutes on first run.
    echo.

    ".venv\Scripts\python.exe" -m pip install -r requirements.txt

    if errorlevel 1 (
        echo.
        echo ERROR: Dependency installation failed.
        echo.
        echo Check requirements.txt and your internet connection.
        pause
        exit /b 1
    )

    echo.
    echo Dependencies installed successfully.

    REM Create marker so next startup is fast.
    echo Setup completed > ".venv\.setup_complete"

) else (

    echo Dependencies already installed.
    echo Skipping first-time package installation.

)

REM ========================================================
REM STEP 5 - Validate important packages
REM ========================================================

echo.
echo [5/6] Validating AI Company environment...

".venv\Scripts\python.exe" -c "from dotenv import load_dotenv; import os; load_dotenv(); key=os.getenv('JWT_SECRET_KEY',''); raise SystemExit(0 if len(key) >= 32 and not key.startswith('GENERATE_') else 1)"

if errorlevel 1 (
    echo.
    echo ERROR: JWT_SECRET_KEY is missing or too short in .env.
    echo Generate a random secret with:
    echo python -c "import secrets; print(secrets.token_urlsafe(48))"
    echo Add it to .env as JWT_SECRET_KEY=your-generated-value.
    echo.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import fastapi, uvicorn, sqlalchemy, pyodbc, pydantic; print('Environment validation successful.')"

if errorlevel 1 (

    echo.
    echo Environment validation failed.
    echo Reinstalling dependencies...
    echo.

    ".venv\Scripts\python.exe" -m pip install -r requirements.txt

    if errorlevel 1 (
        echo.
        echo ERROR: Unable to install required packages.
        pause
        exit /b 1
    )

)

REM ========================================================
REM STEP 6 - Start AI Company
REM ========================================================

echo.
echo [6/6] Starting AI Company...
echo.
echo ========================================================
echo AI COMPANY IS STARTING
echo ========================================================
echo.
echo User Interface:
echo http://127.0.0.1:8000/
echo.
echo Health Check:
echo http://127.0.0.1:8000/health
echo.
echo Press CTRL+C to stop AI Company.
echo ========================================================
echo.

".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

echo.
echo AI Company stopped.
pause

endlocal