@echo off
chcp 65001 >nul
rem Скрипт перезапускает себя из временной папки: иначе обновление файлов
rem на ходу может сбить чтение этого же .bat-файла.
rem Проверка вынесена из блока if: %errorlevel% внутри скобок раскрывается
rem до вызова, и код выхода терялся.
if /i "%~1"=="__run_from_temp" goto :run
copy /y "%~f0" "%TEMP%\project_report_update.bat" >nul 2>&1
call "%TEMP%\project_report_update.bat" __run_from_temp "%~dp0"
set RC=%errorlevel%
del /q "%TEMP%\project_report_update.bat" >nul 2>&1
exit /b %RC%

:run

title Обновление проекта отчётов
cd /d "%~2"
set PORT=8600
set BRANCH=main
set PROJECT_SLUG=Grenlays/project_report
set PROJECT_URL=https://github.com/Grenlays/project_report
set BACKUP_DB=

echo ============================================================
echo  Обновление сервиса отчётов по проектам разработки
echo  Папка: %CD%
echo ============================================================
echo.

rem --- git ---
where git >nul 2>&1
if errorlevel 1 goto :no_git
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 goto :no_repo

rem --- на какой remote смотреть ---
rem Обычно это origin. Если origin смотрит на личный форк, подойдёт remote upstream.
set REMOTE=
git remote get-url origin > "%TEMP%\pr_remote_url.txt" 2>nul
call :url_matches && set REMOTE=origin
if defined REMOTE goto :remote_found
git remote get-url upstream > "%TEMP%\pr_remote_url.txt" 2>nul
call :url_matches && set REMOTE=upstream
:remote_found
del /q "%TEMP%\pr_remote_url.txt" >nul 2>&1
if not defined REMOTE goto :wrong_remote

set SRC_URL=
for /f "delims=" %%u in ('git remote get-url %REMOTE%') do set "SRC_URL=%%u"
echo Источник обновлений: %REMOTE% — %SRC_URL%
echo.

rem --- сервис должен быть остановлен ---
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 goto :port_busy

rem --- локальные правки кода ---
rem data\ — база отчётов этого ПК, __pycache__ — служебный кэш Python: обновлению они не мешают.
rem Сам этот скрипт тоже не мешает: его часто приносят на ПК копией поверх старой версии.
git diff --quiet HEAD -- . ":(exclude)data" ":(exclude,glob)**/__pycache__/**" ":(exclude,literal)Обновить проект.bat"
if errorlevel 1 goto :dirty

rem --- локальная база отчётов ---
rem База лежит в репозитории, но на каждом ПК своя: сохраняем её и возвращаем после обновления.
set BACKUP_DB=%TEMP%\project_report_local_%RANDOM%.sqlite3
if exist "data\reports.sqlite3" (
  copy /y "data\reports.sqlite3" "%BACKUP_DB%" >nul
  if errorlevel 1 (
    echo [ОШИБКА] Не удалось сохранить локальную базу. Обновление отменено.
    set BACKUP_DB=
    pause
    exit /b 1
  )
  echo Локальная база отчётов сохранена.
)

rem --- получить изменения ---
echo.
echo Получаю изменения из репозитория...
git fetch %REMOTE%
if errorlevel 1 (
  echo Повторяю с другим TLS-бэкендом...
  git -c http.sslBackend=openssl fetch %REMOTE%
)
if errorlevel 1 goto :fetch_failed

rem --- свои коммиты, которых нет в проекте ---
set LOCAL_COMMITS=0
for /f "delims=" %%c in ('git rev-list --count %REMOTE%/%BRANCH%..HEAD') do set LOCAL_COMMITS=%%c
if not "%LOCAL_COMMITS%"=="0" goto :local_commits

set NEW=0
for /f "delims=" %%c in ('git rev-list --count HEAD..%REMOTE%/%BRANCH%') do set NEW=%%c
if "%NEW%"=="0" goto :up_to_date

echo.
echo Новые изменения (коммитов: %NEW%):
git --no-pager log --oneline HEAD..%REMOTE%/%BRANCH%

rem --- обновить файлы ---
echo.
echo Обновляю файлы...
git rev-parse --verify refs/heads/%BRANCH% >nul 2>&1
if not errorlevel 1 git checkout -f %BRANCH% >nul 2>&1
git reset --hard %REMOTE%/%BRANCH%
if errorlevel 1 goto :reset_failed

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
exit /b 0


rem ======================= сообщения об ошибках =======================

:url_matches
rem Адрес remote этого ПК указывает на проект? Путь к локальному клону git
rem печатает с обратными слэшами, поэтому проверяем оба написания.
findstr /I /C:"%PROJECT_SLUG%" "%TEMP%\pr_remote_url.txt" >nul && exit /b 0
findstr /I /C:"Grenlays\project_report" "%TEMP%\pr_remote_url.txt" >nul && exit /b 0
exit /b 1

:no_git
echo [ОШИБКА] Git не найден. Установите Git for Windows: https://git-scm.com/download/win
pause
exit /b 1

:no_repo
echo [ОШИБКА] В этой папке нет git-репозитория: %CD%
echo.
echo Скрипт обновляет файлы по истории git, а у этой папки истории нет: похоже,
echo проект скачан ZIP-архивом (Code - Download ZIP) или скопирован без скрытой
echo папки .git. Загрузка файлов на GitHub через сайт локальную историю не создаёт.
echo.
echo Проверьте ещё папку: скрипт работает с той, в которой лежит сам. Если проект
echo лежит в другой папке — скопируйте скрипт туда и запустите оттуда.
echo.
echo Как исправить, нужно один раз:
echo   1. Склонируйте проект в новую папку:
echo        git clone %PROJECT_URL% "%USERPROFILE%\project_report"
echo   2. Перенесите туда свою базу отчётов:
echo        copy "data\reports.sqlite3" "%USERPROFILE%\project_report\data\reports.sqlite3"
echo      Если файла data\reports.sqlite3 нет, шаг пропустите.
echo   3. Дальше работайте в новой папке: «Запустить сервис.bat» и это обновление
echo      запускайте из неё.
echo.
echo Старую папку удалите, когда убедитесь, что отчёты на месте.
pause
exit /b 1

:wrong_remote
echo [ОШИБКА] Обновляться этой папке неоткуда: git-репозиторий есть, но ни один
echo её remote не указывает на проект %PROJECT_SLUG%.
echo.
git remote -v
echo.
echo Так бывает у личного форка: origin смотрит на ваш репозиторий, и изменений
echo проекта в нём нет, поэтому обновление не увидит ничего нового.
echo.
echo Вариант 1, папка должна быть копией проекта:
echo   git remote set-url origin %PROJECT_URL%
echo Вариант 2, оставить свой репозиторий и брать обновления из проекта:
echo   git remote add upstream %PROJECT_URL%
echo.
echo После этого запустите скрипт снова.
pause
exit /b 1

:port_busy
echo Сервис сейчас запущен на порту %PORT%.
echo Сначала остановите его: «Остановить сервис.bat», затем запустите обновление снова.
pause
exit /b 1

:dirty
echo [ОШИБКА] В папке есть локальные правки кода, которые обновление перезапишет:
echo.
git -c core.quotepath=false status --short --untracked-files=no -- . ":(exclude)data" ":(exclude,glob)**/__pycache__/**" ":(exclude,literal)Обновить проект.bat"
echo.
echo Сохраните их (git stash) или отмените (git restore .), затем повторите.
pause
exit /b 1

:fetch_failed
echo [ОШИБКА] Не удалось связаться с репозиторием: %SRC_URL%
echo Проверьте подключение к сети и доступ к %PROJECT_URL%
if exist "%BACKUP_DB%" del /q "%BACKUP_DB%" >nul 2>&1
set BACKUP_DB=
pause
exit /b 1

:local_commits
echo [ВНИМАНИЕ] В папке есть коммиты, которых нет в проекте:
echo.
git --no-pager log --oneline %REMOTE%/%BRANCH%..HEAD
echo.
echo Обновление заменило бы их. Сохраните работу в отдельную ветку:
echo   git branch my-work
echo и запустите скрипт снова.
if exist "%BACKUP_DB%" del /q "%BACKUP_DB%" >nul 2>&1
set BACKUP_DB=
pause
exit /b 1

:reset_failed
echo [ОШИБКА] Не удалось обновить файлы.
if exist "%BACKUP_DB%" echo Локальная база сохранена здесь: %BACKUP_DB%
pause
exit /b 1

:up_to_date
echo.
echo Обновлений нет - уже установлена последняя версия:
git --no-pager log --oneline -1
if exist "%BACKUP_DB%" del /q "%BACKUP_DB%" >nul 2>&1
set BACKUP_DB=
pause
exit /b 0
