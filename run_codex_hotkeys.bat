@echo off
setlocal
set "ROOT=%~dp0"
set "AHK=%ROOT%tools\AutoHotkey\AutoHotkey64.exe"
set "SCRIPT=%ROOT%launch_codex_dictation.ahk"

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
