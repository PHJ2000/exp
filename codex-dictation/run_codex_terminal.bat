@echo off
setlocal
set "APP_DIR=%~dp0"
set "REPO_ROOT=%APP_DIR%..\"
codex -C "%REPO_ROOT%"
