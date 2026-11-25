@echo off
chcp 65001 >nul
title Резервная копия базы отчётов
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=python
where python >nul 2>&1 || set PY=py -3

%PY% backup.py
if errorlevel 1 (
  echo [ОШИБКА] Резервная копия не создана.
) else (
  echo.
  %PY% backup.py list
)
echo.
pause
