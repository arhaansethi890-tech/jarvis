
@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo         JARVIS - Initial Setup
echo ========================================
echo.

:: Check for the Python launcher
where py >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python launcher 'py' was not found.
    echo Install Python 3.10 from https://www.python.org/downloads/
    echo Enable the Python launcher during installation.
    pause
    exit /b 1
)

:: Check for Python 3.10
py -3.10 --version
if errorlevel 1 (
    echo ERROR: Python 3.10 is required.
    echo Install Python 3.10 and run setup.bat again.
    pause
    exit /b 1
)

:: Check required project files
if not exist "requirements.txt" (
    echo ERROR: requirements.txt is missing.
    pause
    exit /b 1
)

if not exist "main.py" (
    echo ERROR: main.py is missing.
    pause
    exit /b 1
)

:: Create virtual environment if needed
if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -3.10 -m venv .venv
    if errorlevel 1 goto :error
)

:: Verify virtual environment Python version
".venv\Scripts\python.exe" -c "import sys; exit(0 if sys.version_info[:2] == (3,10) else 1)"
if errorlevel 1 (
    echo ERROR: Existing .venv does not use Python 3.10.
    echo Rename or remove .venv, then run setup.bat again.
    goto :error
)

echo.
echo Installing Python dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Checking Ollama...
where ollama >nul 2>&1
if errorlevel 1 (
    echo WARNING: Ollama is not installed or not on PATH.
    echo Install it from https://ollama.com
    echo Then run setup.bat again to download the AI model.
    goto :success
)

:: Check whether Ollama API is available
call :ollama_ok
if errorlevel 1 (
    echo Starting Ollama...
    start "" /min ollama serve
)

:: Wait for Ollama API
set "OLLAMA_READY="
for /L %%i in (1,1,30) do (
    call :ollama_ok
    if not errorlevel 1 set "OLLAMA_READY=1"
    if defined OLLAMA_READY goto :ollama_ready
    timeout /t 1 /nobreak >nul
)

echo WARNING: Ollama did not respond within 30 seconds.
echo Start Ollama manually, then run: ollama pull qwen2.5:3b
goto :success

:ollama_ready
echo Ollama is responding.
echo Downloading or verifying qwen2.5:3b...
ollama pull qwen2.5:3b
if errorlevel 1 (
    echo WARNING: Model download failed.
    echo Retry later using: ollama pull qwen2.5:3b
)

:success
echo.
echo ========================================
echo Setup steps completed.
echo Run run.bat to launch JARVIS.
echo ========================================
pause
exit /b 0

:error
echo.
echo SETUP FAILED. Read the error messages above.
pause
exit /b 1

:ollama_ok
powershell -NoProfile -Command "try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0
