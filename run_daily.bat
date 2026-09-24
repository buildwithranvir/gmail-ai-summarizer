@echo off
REM Runs the summarizer with this project's virtual environment.
REM Windows Task Scheduler runs this file every morning (see README).
REM Output (and any errors) are added to summary_log.txt.

cd /d "%~dp0"
"venv\Scripts\python.exe" run.py --scheduled >> summary_log.txt 2>&1
