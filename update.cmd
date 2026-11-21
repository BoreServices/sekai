@echo off
setlocal EnableExtensions

rem ==================== server settings ====================
set "SERVER_USER=freebox"
set "SERVER_HOST=192.168.1.69"
set "REMOTE_DIR=sekai"
rem =========================================================

cd /d "%~dp0"
if errorlevel 1 goto :fail

where scp >nul 2>&1
if errorlevel 1 (
  echo OpenSSH client not found. Enable "OpenSSH Client" in Windows optional features.
  goto :fail
)

echo Ensuring remote directory %REMOTE_DIR% exists...
ssh "%SERVER_USER%@%SERVER_HOST%" "mkdir -p \"%REMOTE_DIR%\""
if errorlevel 1 goto :fail

echo Uploading folder to %SERVER_USER%@%SERVER_HOST%:%REMOTE_DIR% ...
scp -r .\* "%SERVER_USER%@%SERVER_HOST%:%REMOTE_DIR%/"
if errorlevel 1 goto :fail

echo.
echo Uploaded to %SERVER_USER%@%SERVER_HOST%:%REMOTE_DIR%/.
exit /b 0

:fail
echo.
echo Upload failed.
exit /b 1