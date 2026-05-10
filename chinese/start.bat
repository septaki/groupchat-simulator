@echo off
cd /d "%~dp0"
echo.
echo   ==============================
echo     NEST-chat
echo   ==============================
echo.
netstat -ano 2>nul | findstr ":8000 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo   Server already running
    start "" http://localhost:8000
) else (
    echo   Starting server...
    start "NEST-chat" /MIN python server.py
    timeout /t 3 /nobreak >nul
    start "" http://localhost:8000
)
echo.
echo   Close server: double-click close.bat
echo.
pause