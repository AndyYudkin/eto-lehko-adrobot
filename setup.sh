#!/usr/bin/env bash
# One-command setup: creates .env, builds and starts the containers,
# then prints where to open the app and how to log in.
set -euo pipefail
cd "$(dirname "$0")"

die() { echo "Ошибка: $*" >&2; exit 1; }

# set KEY=VALUE in .env (the key is already there, copied from .env.example)
set_env() {
  awk -v k="$1" -v v="$2" 'BEGIN { FS = OFS = "=" }
    $1 == k { print k "=" v; next } { print }' .env > .env.tmp
  mv .env.tmp .env
}

get_env() { grep "^$1=" .env | head -n 1 | cut -d= -f2-; }

random() { LC_ALL=C tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$1" || true; }

command -v docker > /dev/null || die "не найден Docker. Установите Docker Desktop: https://www.docker.com/"
docker compose version > /dev/null 2>&1 || die "не найден Docker Compose (нужна команда «docker compose»)"
docker info > /dev/null 2>&1 || die "Docker не запущен. Запустите Docker Desktop и повторите"

use_existing=n
if [ -f .env ]; then
  read -r -p "Файл .env уже есть. Использовать его? [Y/n] " answer
  case "${answer:-y}" in [nN]*) ;; *) use_existing=y ;; esac
fi

if [ "$use_existing" = n ]; then
  cp .env.example .env
  echo "Создаю .env (адрес Keitaro: $(get_env KT_URL))"

  api_key=""
  while [ -z "$api_key" ]; do
    read -r -p "API-ключ Keitaro: " api_key
  done

  set_env KT_API_KEY "$api_key"
  set_env APP_PASSWORD "$(random 16)"
  set_env JWT_SECRET "$(random 48)"
fi

port="$(get_env APP_PORT)"
port="${port:-8080}"

echo "Собираю и запускаю контейнеры (первый раз это займёт несколько минут)…"
docker compose up -d --build

url="http://localhost:$port"
printf "Жду, пока приложение запустится"
for _ in $(seq 1 60); do
  # the backend is up once /api answers 401 (not logged in) instead of 5xx
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "$url/api/auth/me")" = 401 ]; then
    break
  fi
  printf "."
  sleep 2
done
echo

[ "$(curl -s -o /dev/null -w '%{http_code}' "$url/api/auth/me")" = 401 ] || die "приложение не ответило на $url. Логи: docker compose logs"

cat <<MSG

Готово!
  Адрес:  $url
  Логин:  $(get_env APP_LOGIN)
  Пароль: $(get_env APP_PASSWORD)

Остановить: docker compose down
MSG
