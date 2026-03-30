@echo off
setlocal
set "ROOT=%~dp0"
set "PYTHONW=%ROOT%.venv\Scripts\pythonw.exe"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

if exist "%PYTHONW%" (
  start "" "%PYTHONW%" "%ROOT%codex_dictation.py"
  exit /b 0
)

if exist "%PYTHON%" (
  start "" "%PYTHON%" "%ROOT%codex_dictation.py"
  exit /b 0
)

echo Could not find Python in "%ROOT%.venv\Scripts".
exit /b 1
