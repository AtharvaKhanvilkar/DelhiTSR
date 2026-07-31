@echo off
title DelhiTSR Engine - Auto Restarting Server
echo ========================================================
echo   DelhiTSR Engine - Auto-Restarting Server Supervisor
echo ========================================================
echo.

:SERVER_LOOP
echo [%date% %time%] Launching DelhiTSR Flask Server (app.py)...
.venv\Scripts\python.exe app.py
echo.
echo [%date% %time%] WARNING: Server process exited with code %errorlevel%.
echo [%date% %time%] Auto-restarting server in 2 seconds...
echo.
timeout /t 2 /nobreak >nul
goto SERVER_LOOP
