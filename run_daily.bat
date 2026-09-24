@echo off
REM Double-click this file once to turn on the automatic morning summary.
REM
REM It sets up a Windows task that runs the summarizer whenever you log in to
REM or unlock your laptop, sending at most one summary every 20 hours.
REM After that you never need to run anything by hand (except logging in to
REM Google again roughly once a week, see README).
REM
REM Running it again is safe: it just refreshes the task.

cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_schedule.ps1"
if errorlevel 1 (
    echo.
    echo Could not set up the scheduled task. See the error above.
    pause
    exit /b 1
)

echo.
echo From now on the summary is sent automatically, at most once every 20 hours,
echo shortly after you log in to or unlock this laptop.
echo.
echo Doing a first run now (skipped if a summary went out in the last 20 hours)...
"venv\Scripts\python.exe" run.py --scheduled
echo Done. Check your inbox. If nothing arrived, open summary_log.txt to see why.
echo.
pause
