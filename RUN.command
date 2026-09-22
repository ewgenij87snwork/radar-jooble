#!/bin/bash
set -uo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd -P)"
cd "$ROOT" || exit 1

printf 'RADAR-JOOBLE: sync → поиск 24h → save state → push\n\n'

if [ ! -d ".git" ]; then
  printf 'ОШИБКА: %s не является git checkout radar-jooble.\n' "$ROOT"
  exit 2
fi

CURRENT_BRANCH="$(git branch --show-current 2>/dev/null || true)"
if [ "$CURRENT_BRANCH" != "main" ]; then
  git switch main || { printf 'ОШИБКА: не удалось переключиться на main.\n'; exit 2; }
fi

BEFORE_PULL="$(git rev-parse HEAD 2>/dev/null || true)"
git pull --rebase --autostash origin main || { printf 'ОШИБКА: git pull не выполнен.\n'; exit 2; }
AFTER_PULL="$(git rev-parse HEAD 2>/dev/null || true)"

if [ "$BEFORE_PULL" != "$AFTER_PULL" ] && [ "${RADAR_REEXECED:-0}" != "1" ]; then
  exec env RADAR_REEXECED=1 "$ROOT/RUN.command" "$@"
fi

if [ ! -f ".env.local" ]; then
  printf 'ОШИБКА: не найден .env.local с JOOBLE_API_KEY в %s\n' "$ROOT"
  exit 2
fi
chmod 600 .env.local || { printf 'ОШИБКА: не удалось защитить .env.local\n'; exit 2; }

SUMMARY="$(mktemp -t radar-jooble-summary.XXXXXX)"
trap 'rm -f "$SUMMARY"' EXIT

python3 api-runner.py run --freshness 24h --force >"$SUMMARY"
RUN_RC=$?
cat "$SUMMARY"
printf '\n'

SYNC_RC=0
git add -- state/api-seen.jsonl state/api-usage.json 2>/dev/null || true
if ! git diff --cached --quiet --exit-code; then
  STAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  git -c user.name='Yevgeniy Sorokin' \
      -c user.email='43723531+ewgenij87snwork@users.noreply.github.com' \
      commit -m "state: Jooble run $STAMP" >/dev/null || SYNC_RC=3
fi

if [ "$SYNC_RC" -eq 0 ]; then
  git pull --rebase --autostash origin main >/dev/null || SYNC_RC=3
fi
if [ "$SYNC_RC" -eq 0 ]; then
  git push origin main >/dev/null || SYNC_RC=3
fi

python3 - "$SUMMARY" <<'PY'
import json, pathlib, subprocess, sys
path = pathlib.Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
except Exception:
    raise SystemExit(0)
md = payload.get("markdown")
js = payload.get("jsonl")
print(f"Статус: {payload.get('status', 'UNKNOWN')}")
print(f"24h jobs: {payload.get('recent_unique_jobs', 0)} · MATCH: {payload.get('counts', {}).get('MATCH', 0)} · REVIEW: {payload.get('counts', {}).get('REVIEW', 0)}")
if md and js:
    print("Готовые файлы:")
    print(md)
    print(js)
    if sys.platform == "darwin":
        try:
            subprocess.run(["open", str(pathlib.Path(md).parent)], check=False)
        except OSError:
            pass
PY

if [ "$SYNC_RC" -ne 0 ]; then
  printf '\nПРЕДУПРЕЖДЕНИЕ: результаты созданы, но state не удалось запушить в GitHub.\n'
fi

if [ "$RUN_RC" -ne 0 ]; then
  exit "$RUN_RC"
fi
exit "$SYNC_RC"
