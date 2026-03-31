@echo off
setlocal
set "APP_DIR=%~dp0"
set "REPO_ROOT=%APP_DIR%..\"
set "AHK=%REPO_ROOT%tools\AutoHotkey\AutoHotkey64.exe"
set "SCRIPT=%APP_DIR%launch_codex_dictation.ahk"

if not exist "%AHK%" (
  echo AutoHotkey executable not found: "%AHK%"
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo AutoHotkey script not found: "%SCRIPT%"
  exit /b 1
)

start "" "%AHK%" "%SCRIPT%"
exit /b 0
