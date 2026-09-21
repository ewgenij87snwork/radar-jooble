# RADAR-JOOBLE start

Work only from the physical `radar-jooble` folder. Read `AGENTS.md` first.

## Normal run — default

Browser is not required. Pull the accepted GitHub version, keep the local `.env.local`, and run:

```bash
git pull --ff-only origin main
chmod 600 .env.local
python3 api-runner.py run
```

Use `--force` only when an immediate refresh is intentionally required; it consumes Jooble lifetime API quota:

```bash
python3 api-runner.py run --force
```

The runner prints a JSON summary and creates exactly two user-facing files in `results/`. Контракт: **ровно два** пользовательских файла:
- one `*.md`;
- one `*.jsonl`.

Internal diagnostics remain in `state/api-runs/` and are not part of normal user output.

Transport status `DONE` means every configured API request returned a valid response. If `totalCount` exceeds page-1 results, `coverage_mode=BOUNDED_PAGE1`: usable quota-aware discovery, not exhaustive coverage.

Explicit Remote and Hybrid remain eligible. Explicit Office-only is rejected. Unknown work mode stays `REVIEW` instead of being dropped.

A repeated normal run inside the guard interval may reuse the previous two files without spending API quota.

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
