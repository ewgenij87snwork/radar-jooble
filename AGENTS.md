# RADAR-JOOBLE runtime contract

Работай только из физической папки `radar-jooble`. Сначала проверить `pwd -P`: basename должен быть `radar-jooble`.

Это самостоятельная система. Запрещено читать/использовать state/results соседних RADAR-FAST/OfferStream/radar-папок.

## Default normal path: Jooble REST API

Обычный owner-запуск: `./RUN.command` или двойной клик по `RUN.command`. Launcher сам синхронизирует `main`, делает полный snapshot за `24h`, пишет результаты, затем коммитит и пушит текущую result-пару (`*.md` + `*.jsonl`) вместе с `state/api-seen.jsonl` + `state/api-usage.json`. `results/test/` не архивируется.

Для агента/автоматизации низкоуровневый эквивалент поиска без git-sync: `python3 api-runner.py run --freshness 24h --force`.

Normal run пишет **ровно два пользовательских результата** в `results/`: один Markdown + один JSONL. Internal diagnostics/watermark/lock остаются локально. `state/api-seen.jsonl` и `state/api-usage.json` — намеренно git-synced runtime state; они не содержат API key.

Secret boundary:
- `.env.local` содержит только локальный `JOOBLE_API_KEY=...`;
- runtime парсит его как данные, не `source`/shell;
- mode файла должен быть `0600`;
- ключ нельзя печатать, логировать, класть в results/state diagnostics/ZIP/git/prompt;
- endpoint с ключом нельзя включать в errors/diagnostics;
- API errors не retry автоматически и не запускают browser fallback автоматически;
- `state/api-usage.json` консервативно считает attempts из lifetime quota.

API normal semantics:
- четыре широких quota-aware query, `ResultOnPage=100`, page 1;
- `DONE` означает все configured API requests получили валидный response; если `totalCount > returned`, coverage маркируется `BOUNDED_PAGE1`, а не выдаётся за exhaustive;
- `updated` используется как freshness signal API и явно не называется publication date;
- explicit Remote **и Hybrid** допустимы;
- explicit Office-only отклоняется;
- неизвестный work mode не теряется: `REVIEW`;
- unknown/invalid `updated` не теряется: `REVIEW` с freshness caution;
- main JSONL содержит только MATCH/REVIEW; REJECT хранится только во внутреннем state/diagnostics.

Повторный низкоуровневый normal run без `--force` раньше guard-интервала может вернуть предыдущие два готовых файла без новых API calls. `--force` расходует quota и означает полный свежий snapshot: already-seen вакансии не скрываются, но seen-history обновляется. Owner launcher всегда использует `24h --force`.

## Preserved browser path

Существующий browser crawler сохранён byte-for-byte в `radar.py`, `browser-runner.mjs`, `sources/jooble-adapter.mjs`. Его нельзя переписывать как побочный эффект API-работы. Возврат к нему — только явно через `BROWSER-FALLBACK.md`.

Browser runtime использует только существующий OpenAI browser plugin + Chrome extension surface профиля владельца. Не запускать Chrome через shell, не создавать профиль/окно, не писать альтернативные selectors/collectors.

## Development rule

Classifier/query/output changes сначала проходят offline tests/replay. Live API нужен только для transport/query-semantics evidence; live browser calibration — только для browser/navigation/detail semantics. Не использовать полный browser crawl как default regression loop.
