@echo off
rem Windows setup, the same as setup.sh: creates .env, builds and starts the
rem containers, then prints where to open the app and how to log in.
chcp 65001 >nul
cd /d "%~dp0"

where docker >nul 2>nul || goto no_docker
docker compose version >nul 2>nul || goto no_compose
docker info >nul 2>nul || goto docker_down

if not exist .env goto create
set "ANSWER="
set /p ANSWER="Файл .env уже есть. Использовать его? [Y/n] "
if /i "%ANSWER:~0,1%"=="n" goto create
goto start

:create
copy /y .env.example .env >nul
:ask_key
set "SETUP_KEY="
set /p SETUP_KEY="API-ключ Keitaro: "
if not defined SETUP_KEY goto ask_key
rem set the key and random APP_PASSWORD / JWT_SECRET; write UTF-8 without BOM
powershell -NoProfile -Command ^
  "$chars = [char[]]'abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';" ^
  "function New-Secret($n) { -join (1..$n | ForEach-Object { $chars | Get-Random }) }" ^
  "$set = @{ KT_API_KEY = $env:SETUP_KEY; APP_PASSWORD = New-Secret 16; JWT_SECRET = New-Secret 48 };" ^
  "$path = Join-Path (Get-Location) '.env';" ^
  "$lines = [IO.File]::ReadAllLines($path) | ForEach-Object { $k = ($_ -split '=', 2)[0]; if ($set.ContainsKey($k)) { $k + '=' + $set[$k] } else { $_ } };" ^
  "[IO.File]::WriteAllLines($path, [string[]]$lines)"
if errorlevel 1 goto env_failed

:start
set "APP_PORT=8080"
for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
  if "%%A"=="APP_PORT" set "APP_PORT=%%B"
  if "%%A"=="APP_LOGIN" set "APP_LOGIN=%%B"
  if "%%A"=="APP_PASSWORD" set "APP_PASSWORD=%%B"
)
set "URL=http://localhost:%APP_PORT%"

echo Собираю и запускаю контейнеры, первый раз это займёт несколько минут...
docker compose up -d --build || goto compose_failed

echo Жду, пока приложение запустится...
set /a TRIES=0
:wait
rem the backend is up once /api answers 401 (not logged in) instead of 5xx
set "CODE="
for /f %%C in ('curl -s -o NUL -w "%%{http_code}" "%URL%/api/auth/me"') do set "CODE=%%C"
if "%CODE%"=="401" goto ready
set /a TRIES+=1
if %TRIES% geq 60 goto not_ready
timeout /t 2 /nobreak >nul
goto wait

:ready
echo.
echo Готово!
echo   Адрес:  %URL%
echo   Логин:  %APP_LOGIN%
echo   Пароль: %APP_PASSWORD%
echo.
echo Остановить: docker compose down
pause
exit /b 0

:no_docker
echo Ошибка: не найден Docker. Установите Docker Desktop: https://www.docker.com/
goto fail
:no_compose
echo Ошибка: не найден Docker Compose, нужна команда "docker compose"
goto fail
:docker_down
echo Ошибка: Docker не запущен. Запустите Docker Desktop и повторите
goto fail
:env_failed
echo Ошибка: не удалось записать .env
goto fail
:compose_failed
echo Ошибка: docker compose не смог запустить контейнеры
goto fail
:not_ready
echo Ошибка: приложение не ответило на %URL%. Логи: docker compose logs
goto fail
:fail
pause
exit /b 1
