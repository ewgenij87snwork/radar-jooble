# RADAR-JOOBLE development

Цель: кратчайший надёжный цикл разработки без повторного сжигания live browser/API ресурса.

1. API/classifier/output change → offline unit + end-to-end fixture tests.
2. API transport/query semantics → один bounded live API smoke, только когда это действительно нужно.
3. Browser navigation/detail semantics → отдельный browser calibration по `BROWSER-FALLBACK.md`.
4. Не использовать полный live browser crawl для проверки Python regex/state/rendering.
5. Не менять preserved browser runtime при API-only работе.

## Normal reliability

API — primary low-cost discovery. Four page-1 broad queries use at most four requests per fresh normal run; quota accounting fail-closes before the documented lifetime ceiling. Page-1 truncation is explicit `BOUNDED_PAGE1`, not fake exhaustive coverage.

Freshness uses Jooble API `updated`, which is an update timestamp, not publication date. First/normal bootstrap uses 3d; after pause it expands to 7d. Unknown `updated` remains visible only as REVIEW.

Seen-state is keyed by canonical JDP id when available, otherwise API id. Same vacancy is resurfaced when its `updated` timestamp or decision changes under the current ruleset.

## Browser preservation

The browser transport and accumulated evidence are retained as a fallback/stronger-detail path. API-first adoption never deletes the 13-route browser implementation or its calibration patches.
