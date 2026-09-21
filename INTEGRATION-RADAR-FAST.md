# Future RADAR-FAST Jooble integration

This repository remains autonomous. RADAR-FAST must not read or import this repository's `state/` or `results/`, and RADAR-JOOBLE must not depend on RADAR-FAST.

The portable browser unit is `sources/jooble-adapter.mjs`. A future multi-source browser runner can register it as:

```js
ADAPTERS["Jooble"] = joobleAdapter;
```

The adapter exposes a source descriptor plus `collectList(ctx)` and `collectDetail(tab, url, deadline)`. It owns Jooble listing carriers, signed JDP identity, `/desc` detail acquisition, freshness and exhaustion evidence, and challenge detection. It does not know about MATCH/REVIEW/REJECT, Markdown, JSONL, `radar.py`, `state`, or `results`.

## RADAR-FAST state/config additions for a future integration

RADAR-FAST would need to add these source-layer facts in its own state/config, without importing this repository:

- `"Jooble"` in `SOURCES`;
- a Jooble source document and source-specific host allowlist;
- `^/jdp/-?\d+(?:[-/]|$)` as the signed `/jdp/` vacancy identity regex;
- the nine production routes from `joobleSource.routes`;
- Jooble freshness parameters `24h → date=8`, `3d → date=2`, `7d → date=3`;
- Jooble coverage and terminal semantics (`NO_NEXT` / `NO_NEW_URLS`);
- adapter registration through `ADAPTERS["Jooble"] = joobleAdapter`;
- independent source state/results owned by RADAR-FAST itself.

Important RADAR-FAST source policy: Jooble promoted / `Запропоновані` cards remain in the
candidate universe. The generic organic filter must be disabled for this adapter, for example:

```python
SOURCE_POLICY["Jooble"] = {"excludePromoted": False}
```

RADAR-FAST must preserve the adapter's `promoted` metadata while applying the standalone
listing prefilter and detail classification policy. Standalone `state/` and `results/` remain
independent from RADAR-FAST state/results.

The adapter's ephemeral carrier cache is per run. If a new process lacks the `/desc` carrier for a JDP identity, `collectDetail` fails closed with a controlled cache-missing error; it never invents a carrier from a title or company.
