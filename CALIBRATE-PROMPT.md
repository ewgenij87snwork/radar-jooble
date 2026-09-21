ЦЕЛЬ → полностью проверить RADAR-JOOBLE на живом Jooble и вернуть один самодостаточный calibration bundle.

ЧТО ДЕЛАТЬ → работай только в текущей физической папке `radar-jooble`. Прочитай `AGENTS.md` и `start.md`. Ничего в runtime не редактируй. Запусти режим TEST (`startArgs: ["--test-live"]`) строго через wrappers из `start.md` и повторяй runner-wrapper до terminal status. `CONTINUE`/`PROGRESS` — продолжай. `BLOCKED` — зафиксируй причину и повтори wrapper, чтобы runner завершил PARTIAL и собрал diagnostics. При `RUNNER_ERROR` остановись, не пиши обходной browser-код.

ПОЧЕМУ → TEST сам соберёт route/card/filter/classification diagnostics и упакует их вместе с точной версией runtime; ручной копипаст не нужен.

На `DONE` верни только: status, elapsed, Jooble cards/candidates/resolved, MATCH/REVIEW/CONFIRMED, blocker если есть, `markdown_link`, `jsonl_link`, `calibration_bundle_link`. Не читай и не используй `RADAR-FAST`.
