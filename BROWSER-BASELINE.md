# Browser path baseline — preserved

This file records the useful browser findings so API-first work does not erase them.

The executable browser path remains unchanged in:
- `radar.py`
- `browser-runner.mjs`
- `sources/jooble-adapter.mjs`
- `BROWSER-FALLBACK.md`

## Proven useful state from 2026-09-21 calibration history

A stable 3-day production calibration reached all 13 production routes, 177 unique listing cards, 75 safe listing rejects, 102 detail-shortlist candidates, and 20 resolved details before two consecutive unrecovered Jooble challenges opened the detail circuit. Main result for that run was 13 MATCH / 5 REVIEW / 79 REJECT (3 resolved REVIEW + 2 blocked-detail REVIEW). The scoped detail fallback no longer used whole `main/body` vacancy text and the previously contaminated `Middle Backend Developer (Node.js) @ MasterBorn` classified as MATCH rather than a false >5y reject.

Bare technology calibration produced real incremental listing discovery versus the 13 production routes in the clean first sweep:
- `nestjs`: 1 unique / +0 incremental;
- `typescript`: 21 / +9;
- `javascript`: 68 / +24;
- `react`: 68 / +15 in the 02:59 run; a later first sweep observed 51 / +13, demonstrating Jooble variability;
- `nodejs`, `node.js`, `angular`: calibration remained blocked/uncertain because freshness UI proof diverged from the preserved `date=2` URL before subsequent Cloudflare pressure.

A later 03:25 run demonstrated why browser calibration is expensive: discovery reached 230 cards but detail resolution hit challenge before any detail was accepted. The 10:44 run was blocked on the first `angular developer` production route by Cloudflare security verification.

These are browser observations, not API assumptions. API-first must not delete or reinterpret them.
