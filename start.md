# RADAR-JOOBLE start

Work only from the physical `radar-jooble` folder. Read `AGENTS.md` first.

## Обычный запуск владельца

Одна команда:

```bash
./run.command
```

`run.command` сам:
1. переключается на `main` и делает `git pull --rebase --autostash origin main`;
2. при обновлении launcher немедленно перезапускает уже новую версию;
3. запускает полный свежий Jooble API snapshot за последние `24h`;
4. создаёт ровно два пользовательских файла в `results/`: один `*.md` и один `*.jsonl`;
5. обновляет `state/api-seen.jsonl` и `state/api-usage.json`;
6. коммитит текущую пару результата (`*.md` + `*.jsonl`) и эти два runtime-state файла, подтягивает свежий `main` и пушит всё это в GitHub;
7. открывает папку `results/`.

`.env.local`, watermark, lock, diagnostics и `results/test/` в Git не пушатся. Каждая обычная result-пара архивируется в Git history.

На первом запуске после старой версии допустим один bootstrap:

```bash
git pull --ff-only origin main && ./run.command
```

После этого всегда достаточно только `./run.command`.

## Низкоуровневый эквивалент поиска

Для отладки без git-sync:

```bash
python3 api-runner.py run --freshness 24h --force
```

`--force` означает **полный свежий snapshot** текущего freshness-window: already-seen вакансии не скрываются, но history всё равно обновляется. Каждый такой запуск расходует Jooble API quota.

Transport status `DONE` означает, что все configured API requests получили валидный response. Если `totalCount` больше page-1 results, `coverage_mode=BOUNDED_PAGE1`: это quota-aware discovery, не exhaustive coverage.

Freshness `24h` основан на Jooble API `updated`, а не на publication date. Имя result-файла показывает фактическое окно freshness, а не длительность выполнения.

## Offline verification

```bash
python3 selftest.py
```

Optional developer suite when pytest is already installed:

```bash
python3 -m pytest -q
```

## Explicit browser fallback

The preserved browser crawler is never launched automatically on an API error. Return to it only by explicit decision and follow `BROWSER-FALLBACK.md`.
