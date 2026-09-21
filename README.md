# RADAR-JOOBLE

Standalone Jooble job radar with an official-API default path and a preserved browser fallback.

## Normal use

Keep your regional Jooble key only in local `.env.local`:

```text
JOOBLE_API_KEY=...
```

Then:

```bash
git pull --ff-only origin main
chmod 600 .env.local
python3 api-runner.py run
```

Normal output is exactly one Markdown plus one JSONL under `results/`.

- official Jooble REST API is the default discovery transport;
- API `updated` is treated as update/freshness evidence, not publication date;
- Remote and Hybrid remain eligible;
- unknown work mode remains `REVIEW`;
- page-1 truncation is reported as `BOUNDED_PAGE1`, never as exhaustive coverage;
- local seen-state prevents repeated unchanged results;
- browser implementation remains available explicitly through `BROWSER-FALLBACK.md`.

Runtime uses only the Python standard library. Offline verification:

```bash
python3 selftest.py
```
