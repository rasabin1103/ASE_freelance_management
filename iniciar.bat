@echo off
setlocal
cd /d "%~dp0"
title Cuenta Clara
where python >nul 2>nul
if errorlevel 1 (
    echo No se encuentra Python. Instala Python 3 y activa la opcion de agregarlo al PATH.
    pause
    exit /b 1
)
python launcher.py
if errorlevel 1 pause
