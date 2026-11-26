@echo off
chcp 65001 >nul
rem Скрипт перезапускает себя из временной папки: иначе обновление файлов
rem на ходу может сбить чтение этого же .bat-файла.
if /i not "%~1"=="__run_from_temp" (
  copy /y "%~f0" "%TEMP%\project_report_update.bat" >nul 2>&1
  call "%TEMP%\project_report_update.bat" __run_from_temp "%~dp0"
  set RC=%errorlevel%
  del /q "%TEMP%\project_report_update.bat" >nul 2>&1
  exit /b %RC%
)

title Обновление проекта отчётов
cd /d "%~2"
set PORT=8600
set REMOTE=origin
set BRANCH=main

echo ============================================================
echo  Обновление сервиса отчётов по проектам разработки
echo  Папка: %CD%
echo ============================================================
echo.

rem --- git ---
where git >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Git не найден. Установите Git for Windows: https://git-scm.com/download/win
  pause
  exit /b 1
)
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Эта папка не является git-репозиторием.
  echo Скопируйте проект заново: git clone https://github.com/Grenlays/project_report
  pause
  exit /b 1
)

rem --- сервис должен быть остановлен ---
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo Сервис сейчас запущен на порту %PORT%.
  echo Сначала остановите его: «Остановить сервис.bat», затем запустите обновление снова.
  pause
  exit /b 1
)

rem --- локальные правки кода ---
rem data\ — база отчётов этого ПК, __pycache__ — служебный кэш Python: обновлению они не мешают.
set LOCAL=
for /f "delims=" %%f in ('git status --porcelain --untracked-files=no -- . ":(exclude)data" ":(exclude,glob)**/__pycache__/**"') do set LOCAL=1
if defined LOCAL (
  echo [ОШИБКА] В папке есть локальные правки кода, которые обновление перезапишет:
  echo.
  git status --short --untracked-files=no -- . ":(exclude)data" ":(exclude,glob)**/__pycache__/**"
  echo.
  echo Сохраните их ^(git stash^) или отмените ^(git restore .^), затем повторите.
  pause
  exit /b 1
)

rem --- локальная база отчётов ---
rem База лежит в репозитории, но на каждом ПК своя: сохраняем её и возвращаем после обновления.
set BACKUP_DB=%TEMP%\project_report_local_%RANDOM%.sqlite3
if exist "data\reports.sqlite3" (
  copy /y "data\reports.sqlite3" "%BACKUP_DB%" >nul
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось сохранить локальную базу. Обновление отменено.
    pause
    exit /b 1
  )
  echo Локальная база отчётов сохранена.
)

rem --- получить изменения ---
echo.
echo Получаю изменения из репозитория...
git fetch %REMOTE% %BRANCH%
if errorlevel 1 (
  echo Повторяю с другим TLS-бэкендом...
  git -c http.sslBackend=openssl fetch %REMOTE% %BRANCH%
)
if errorlevel 1 (
  echo [ОШИБКА] Не удалось связаться с репозиторием.
  echo Проверьте подключение к сети и доступ к https://github.com/Grenlays/project_report
  set BACKUP_DB=
  pause
  exit /b 1
)

set NEW=0
for /f "delims=" %%c in ('git rev-list --count HEAD..%REMOTE%/%BRANCH%') do set NEW=%%c
if "%NEW%"=="0" (
  echo.
  echo Обновлений нет — уже установлена последняя версия:
  git --no-pager log --oneline -1
  set BACKUP_DB=
  pause
  exit /b 0
)

echo.
echo Новые изменения ^(коммитов: %NEW%^):
git --no-pager log --oneline HEAD..%REMOTE%/%BRANCH%

rem --- обновить файлы ---
echo.
echo Обновляю файлы...
git rev-parse --verify refs/heads/%BRANCH% >nul 2>&1
if not errorlevel 1 git checkout -f %BRANCH% >nul 2>&1
git reset --hard %REMOTE%/%BRANCH%
if errorlevel 1 (
  echo [ОШИБКА] Не удалось обновить файлы.
  if exist "%BACKUP_DB%" echo Локальная база сохранена здесь: %BACKUP_DB%
  pause
  exit /b 1
)

if exist "%BACKUP_DB%" (
  copy /y "%BACKUP_DB%" "data\reports.sqlite3" >nul
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось вернуть локальную базу. Она сохранена здесь: %BACKUP_DB%
  ) else (
    del /q "%BACKUP_DB%" >nul 2>&1
    echo Локальная база отчётов возвращена на место.
  )
)

rem --- проверка ---
set PY=
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py -3
if defined PY (
  echo.
  echo Проверяю обновлённую версию тестами...
  set PYTHONIOENCODING=utf-8
  %PY% -m unittest discover -s tests -q
  if errorlevel 1 (
    echo [ВНИМАНИЕ] Тесты не прошли — смотрите вывод выше.
  ) else (
    echo Тесты пройдены.
  )
) else (
  echo.
  echo Python не найден — проверку тестами пропускаю.
)

echo.
echo Готово. Установленная версия:
git --no-pager log --oneline -3
echo.
echo Запустить сервис: «Запустить сервис.bat»
pause
