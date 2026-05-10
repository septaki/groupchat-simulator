@echo off
echo.
echo   ==============================
echo     NEST-chat - Close Server
echo   ==============================
echo.
taskkill /IM python.exe /F >nul 2>&1
if not errorlevel 1 (
    echo   Server closed
) else (
    echo   No server found
)
echo.
pause