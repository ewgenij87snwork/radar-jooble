# RADAR-JOOBLE

Standalone Jooble job radar with an official-API default path and a preserved browser fallback.

## Normal use

Keep the Jooble key only in local `.env.local`:

```text
JOOBLE_API_KEY=...
```

Then use one command:

```bash
./RUN.command
```

The launcher pulls the current `main`, runs a **full 24h snapshot**, writes exactly one Markdown plus one JSONL under `results/`, updates runtime history, then commits the current result pair plus `state/api-seen.jsonl` + `state/api-usage.json` and pushes them back to GitHub.

`.env.local`, watermark, diagnostics, locks and `results/test/` stay local. Because this repository is public, archived result pairs and the intentionally synced `api-seen.jsonl` job-history state are also public.

- official Jooble REST API is the default discovery transport;
- API `updated` is treated as freshness evidence, not publication date;
- forced owner runs return the whole current 24h snapshot even for already-seen jobs;
- Remote and Hybrid remain eligible;
- unknown work mode remains `REVIEW`;
- page-1 truncation is reported as `BOUNDED_PAGE1`, never as exhaustive coverage;
- browser implementation remains available explicitly through `BROWSER-FALLBACK.md`.

Low-level equivalent without git sync:

```bash
python3 api-runner.py run --freshness 24h --force
```

Offline verification:

```bash
python3 selftest.py
```
