#!/bin/bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd -P)"
cd "$ROOT" || exit 1

finish() {
  printf '\nНажмите Enter, чтобы закрыть окно.\n'
  read -r _
}
trap finish EXIT

printf 'RADAR-JOOBLE: запуск поиска вакансий...\n\n'

if [ ! -f ".env.local" ]; then
  printf 'ОШИБКА: не найден .env.local с JOOBLE_API_KEY в %s\n' "$ROOT"
  exit 2
fi
chmod 600 .env.local || { printf 'ОШИБКА: не удалось защитить .env.local\n'; exit 2; }

SUMMARY="$(mktemp -t radar-jooble-summary.XXXXXX)"
trap 'rm -f "$SUMMARY"; finish' EXIT

python3 api-runner.py run >"$SUMMARY"
RC=$?
cat "$SUMMARY"
printf '\n'

python3 - "$SUMMARY" <<'PY'
import json, pathlib, subprocess, sys
path = pathlib.Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
except Exception:
    raise SystemExit(0)
md = payload.get("markdown")
js = payload.get("jsonl")
status = payload.get("status", "UNKNOWN")
print(f"Статус: {status}")
if md and js:
    print("Готовые файлы:")
    print(md)
    print(js)
    if sys.platform == "darwin":
        for item in (md, js):
            try:
                subprocess.run(["open", "-R", item], check=False)
            except OSError:
                pass
PY

exit "$RC"
