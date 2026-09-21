# Jooble maintenance note

## Search contract

RADAR-JOOBLE использует только `ua.jooble.org` и direct vacancy identity `/jdp/<signed-numeric-id>`. JDP id бывает как положительным, так и отрицательным.

Production маршруты: `angular developer`, `react developer`, `frontend developer`, `front end developer`, `frontend engineer`, `typescript developer`, `javascript developer`, `full stack developer`, `fullstack engineer`, `node.js developer`, `nestjs developer`, `ai developer`, `ai engineer`. В TEST calibration сразу после production discovery и до detail sweep выполняются bare technology probes: `nestjs`, `nodejs`, `node.js`, `typescript`, `javascript`, `react`, `angular`. Production routes по-прежнему требуют доказанный Remote+freshness. Calibration probe разделяет эти доказательства: если Remote path после Jooble navigation не доказан, выдача может сканироваться как `SCANNED_UNFILTERED_LOCATION`; если UI freshness-control не найден, но resolved URL точно сохранил `date=<freshness>`, probe может сканироваться только как `SCANNED_URL_FRESHNESS_ONLY`. Эти ослабленные статусы используются исключительно для измерения recall и не являются production proof/promotion. Если даже URL потерял нужный `date`, probe остаётся `BLOCKED`. Diagnostics также rehydrate production JDP ids и уже завершённые probes после runner restart, поэтому один TEST run не должен повторно пересчитывать probes с пустым baseline. Для каждого probe diagnostics сохраняет requested/resolved URL, `date` param/control и Remote path/control. Оба Node spelling проверяются отдельно, потому что Jooble может нормализовать или искать их по-разному.

Jooble — агрегатор с fuzzy/personalized выдачей. Поэтому route сам по себе не означает, что каждая карточка целевая. Все карточки, включая promoted/`Запропоновані`, внутри доказанного remote+freshness-window дедуплицируются по JDP id; затем только shortlist проходит detail page.

Каждый production route использует Jooble location path после search slug: `/работа-<query>/Віддалено` (серверные aliases `/Удаленно` и `/remote` допустимы после navigation). Route обязан доказать одновременно Remote location path, remote UI/filter и `date=<freshness>` + freshness UI. `l=Remote` не считается доказательством Remote. Потеря remote path/filter после navigation/pagination — fail-closed.

## Freshness

Критично: freshness-filter Jooble относится к моменту появления вакансии в индексе Jooble, а дата на вакансии может быть датой исходного сайта. Поэтому runtime НЕ использует видимую publication date как границу покрытия и НЕ понижает MATCH до REVIEW только из-за отсутствующей detail publication date, если route freshness уже доказан.

Runtime применяет overlap-фильтр и обязан доказать одновременно:
1. resolved search URL сохраняет ожидаемый `date=<param>`;
2. на странице присутствует Jooble date-filter UI/evidence;
3. вся отфильтрованная выдача исчерпана через pagination/load-more до `NO_NEXT`/`NO_NEW_URLS`.

Профили freshness:
- `24h` → `date=8` — только calibration TEST;
- `3d` → `date=2` — обычный ежедневный overlap/bootstrap;
- `7d` → `date=3` — автоматическое расширение после паузы до 6 дней.

Если последняя доказанная normal coverage старше 6 дней, runtime fail-closed: не выдаёт ложный `COMPLETE`.

## Portable adapter and extraction

`sources/jooble-adapter.mjs` is the standalone Jooble browser unit. Listing discovery accepts direct `/jdp/<signed-id>` evidence, but its primary live carrier is Jooble's `/desc/<signed-id>?…` link plus the signed numeric DOM/app-state identity. The adapter resolves that carrier to an observed canonical JDP link before emitting a card. Negative IDs are first-class.

LIST: `/desc` carriers, structured state/JSON-LD, then semantic DOM fallback; direct `/jdp/` anchors are not required. Pagination: `rel=next`/semantic next, then controlled load-more/scroll with zero-growth proof.

DETAILS: adapter сначала переиспользует доказанный structured `JobPosting` из listing state, если он уже содержит полный detail payload; иначе использует observed `/desc` carrier и извлекает runtime state/JSON-LD перед normal DOM fallback. Discovery never opens carriers merely to resolve identity: canonical identity is deterministic `https://ua.jooble.org/jdp/<signed-id>`. Every card preserves its originating SERP for one bounded challenge recovery attempt per detail. One unrecovered challenge blocks only that detail; the production circuit opens only after two consecutive unrecovered detail challenges. A missing carrier, identity mismatch, or security verification page remains a controlled unresolved failure.

Every run records `DISCOVERY_COMPLETE`, `DETAILS_COMPLETE`, and `CLASSIFICATION_COMPLETE` evidence separately. A source/run may be `COMPLETE` only after all candidate details are valid or the source is correctly fail-closed.

DETAILS: JSON-LD `JobPosting` предпочтителен; fallback — `h1` + минимальный DOM ancestor с достаточным vacancy text и без чужих `/jdp/`/`/desc/` job links. Весь `main`/`body` не используется как detail text: это смешивает соседние вакансии и может давать ложные experience/travel/client gates. Final direct JDP id обязан совпасть.

Final filtering повторяет target rules RADAR-FAST, плюс Jooble-specific hard gate `NOT_TARGET_WEB_JS` для fuzzy-мусора. Основные output-файлы содержат только MATCH/REVIEW; REJECT остаётся в calibration diagnostics/own seen-state и не засоряет результаты.


Detail shortlist не сортируется по JDP id: runtime обрабатывает сначала наиболее вероятные Node/Nest и core web title-lanes, затем AI title-lanes, затем остальные кандидаты. Explicit non-JS primary-stack titles получают priority penalty (но не исчезают из shortlist), а явные non-target specialties отбрасываются listing-level даже при вторичном TypeScript/React упоминании. Это меняет только порядок/стоимость detail work и не ослабляет fail-closed rules.
