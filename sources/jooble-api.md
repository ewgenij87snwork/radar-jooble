# Jooble REST API transport

Official references checked 2026-09-21:
- https://help.jooble.org/en/support/solutions/articles/60001448238
- https://help.jooble.org/en/support/solutions/articles/60000922689-how-to-connect-to-the-jooble-rest-api
- https://ua.jooble.org/api/about

Runtime contract:
- regional endpoint: `POST https://ua.jooble.org/api/{key}`;
- JSON fields used: `keywords`, `location`, `page`, `ResultOnPage`, `SearchMode`, `companysearch`;
- response fields consumed: `totalCount`, and job `id/title/location/snippet/salary/source/type/link/company/updated`;
- free-key quota is treated as lifetime-scarce; runtime keeps conservative attempt accounting and stops before the documented ceiling.

## Query strategy

Four broad page-1 queries combine the already-proven browser lanes with bare technologies. This intentionally avoids duplicating every developer/engineer spelling while retaining the preserved 13-route browser fallback for stronger/alternate coverage.

All queries use documented country location `Ukraine`. The official API documents location as city/region/country, so the runtime does not depend on undocumented `Remote` as a location value. Remote/Hybrid eligibility is determined from each returned job's title/location/snippet. The dedicated hybrid query keeps explicit hybrid keywords for recall.

## Work-mode semantics

- explicit Remote → eligible;
- explicit Hybrid → eligible;
- explicit Office-only → REJECT;
- unknown format → REVIEW.

This preserves the useful hybrid lane from the browser implementation and prevents false-negative dropping when API listing evidence does not explicitly state format.

## Freshness

`updated` is not publication date. Runtime uses it only as API freshness/update evidence. Stale known timestamps are suppressed from the active window; missing/invalid timestamps stay visible as REVIEW with an explicit caution.

## Coverage

Normal mode intentionally spends one request per configured broad query, page 1, up to 100 jobs. When `totalCount > returned`, output marks `BOUNDED_PAGE1`; it does not claim exhaustive API coverage. Browser fallback remains available when stronger/exhaustive evidence is worth the cost.

## Secret boundary

`.env.local` is local-only, parsed as data, mode 0600, and excluded from clean artifacts. The key and endpoint containing it must never appear in errors, outputs, diagnostics, ZIPs, or prompts.
