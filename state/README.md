# State

Historical `radar-jooble-*.patch` files are preserved browser-development evidence.

Runtime API state files are created locally and are intentionally not shipped in clean builds:
- `api-seen.jsonl`
- `api-usage.json`
- `api-watermark.json`
- `api-run.lock`
- `api-runs/`

Do not place `.env.local` or API keys under `state/`.
