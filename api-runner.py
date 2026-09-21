#!/usr/bin/env python3
"""Official-API discovery runner for RADAR-JOOBLE.

Normal mode writes exactly two user-facing files in results/: Markdown + JSONL.
Internal diagnostics/state stay under state/.  The preserved browser crawler is
an explicit fallback and is never invoked automatically.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import html
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import radar

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "sources" / "jooble-api.json"
ENV_PATH = ROOT / ".env.local"
RESULTS_DIR = ROOT / "results"
TEST_RESULTS_DIR = ROOT / "results" / "test" / "api"
STATE_DIR = ROOT / "state"
RUN_DIAGNOSTICS_DIR = STATE_DIR / "api-runs"
SEEN_PATH = STATE_DIR / "api-seen.jsonl"
USAGE_PATH = STATE_DIR / "api-usage.json"
WATERMARK_PATH = STATE_DIR / "api-watermark.json"
LOCK_PATH = STATE_DIR / "api-run.lock"

API_RULESET_VERSION = "2026-09-21.api2"
API_SCHEMA_VERSION = 2
API_QUOTA_LIFETIME = 500
API_QUOTA_SOFT_LIMIT = 450
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
HTTP_TIMEOUT_SECONDS = 20
MIN_NORMAL_INTERVAL = timedelta(hours=20)
ALLOWED_HOSTS = {"ua.jooble.org", "www.ua.jooble.org"}
FRESHNESS = {"24h": timedelta(days=1), "3d": timedelta(days=3), "7d": timedelta(days=7)}
JDP_RE = re.compile(r"/jdp/(-?\d+)(?:[-/]|$)", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
REMOTE_RE = re.compile(r"\b(?:remote|віддал\w*|удален\w*|дистанційн\w*)\b", re.IGNORECASE)
HYBRID_RE = re.compile(r"\b(?:hybrid|гібрид\w*|гибрид\w*)\b", re.IGNORECASE)
OFFICE_RE = re.compile(r"\b(?:office|офіс\w*|офис\w*|on[- ]?site|onsite)\b", re.IGNORECASE)


class ApiRunnerError(RuntimeError):
    pass


@dataclass(frozen=True)
class Query:
    query_id: str
    keywords: str
    location: str


@dataclass
class ApiResponse:
    query: Query
    total_count: int
    jobs: list[dict[str, Any]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def compact(value: Any, limit: int = 20_000) -> str:
    text = html.unescape(str(value or ""))
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


@contextlib.contextmanager
def exclusive_run_lock() -> Iterable[None]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ApiRunnerError("another RADAR-JOOBLE API run is already active") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiRunnerError("sources/jooble-api.json is missing or invalid") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != 2:
        raise ApiRunnerError("Jooble API config schema_version must be 2")
    location = compact(raw.get("location"), 120)
    result_on_page = raw.get("result_on_page")
    if not location:
        raise ApiRunnerError("Jooble API config requires a location")
    if isinstance(result_on_page, bool) or not isinstance(result_on_page, int) or not 1 <= result_on_page <= 100:
        raise ApiRunnerError("Jooble API result_on_page must be in 1..100")
    queries_raw = raw.get("queries")
    if not isinstance(queries_raw, list) or not queries_raw:
        raise ApiRunnerError("Jooble API config requires queries")
    queries: list[Query] = []
    ids: set[str] = set()
    for item in queries_raw:
        if not isinstance(item, dict):
            raise ApiRunnerError("every Jooble API query must be an object")
        query_id = compact(item.get("id"), 80)
        keywords = compact(item.get("keywords"), 700)
        if not query_id or not keywords or query_id in ids:
            raise ApiRunnerError("query ids/keywords must be non-empty and ids unique")
        ids.add(query_id)
        query_location = compact(item.get("location"), 120) or location
        queries.append(Query(query_id, keywords, query_location))
    search_mode = raw.get("search_mode", 0)
    if isinstance(search_mode, bool) or not isinstance(search_mode, int):
        raise ApiRunnerError("search_mode must be integer")
    return {
        "location": location,
        "result_on_page": result_on_page,
        "search_mode": search_mode,
        "companysearch": bool(raw.get("companysearch", False)),
        "queries": queries,
    }


def load_api_key(path: Path = ENV_PATH) -> str:
    try:
        stat = path.stat()
        if stat.st_mode & 0o077:
            raise ApiRunnerError(".env.local permissions are too broad; require 0600")
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ApiRunnerError(".env.local is missing") from exc
    except OSError as exc:
        raise ApiRunnerError(".env.local cannot be read") from exc
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() != "JOOBLE_API_KEY":
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values.append(value.strip())
    if len(values) != 1 or not values[0]:
        raise ApiRunnerError(".env.local must contain exactly one non-empty JOOBLE_API_KEY")
    if any(ch.isspace() for ch in values[0]):
        raise ApiRunnerError("JOOBLE_API_KEY contains whitespace")
    return values[0]


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiRunnerError(f"state file is invalid: {path.name}") from exc
    if not isinstance(value, dict):
        raise ApiRunnerError(f"state file is invalid: {path.name}")
    return value


def reserve_request_slot() -> int:
    state = read_json(USAGE_PATH, {"schema_version": 1, "attempted": 0, "successful": 0})
    attempted = int(state.get("attempted", 0))
    if attempted >= API_QUOTA_SOFT_LIMIT:
        raise ApiRunnerError(f"Jooble API soft quota limit reached ({attempted}/{API_QUOTA_LIFETIME})")
    attempted += 1
    state.update(
        schema_version=1,
        attempted=attempted,
        quota=API_QUOTA_LIFETIME,
        soft_limit=API_QUOTA_SOFT_LIMIT,
        last_attempt_at=utc_now().isoformat(),
    )
    atomic_write_json(USAGE_PATH, state)
    return attempted


def mark_request_success() -> None:
    state = read_json(USAGE_PATH, {"schema_version": 1, "attempted": 0, "successful": 0})
    state["successful"] = int(state.get("successful", 0)) + 1
    state["last_success_at"] = utc_now().isoformat()
    atomic_write_json(USAGE_PATH, state)


def parse_iso_timestamp(value: Any) -> datetime | None:
    raw = compact(value, 120)
    if not raw:
        return None
    raw = raw.replace("Z", "+00:00")
    raw = re.sub(r"(\.\d{6})\d+(?=(?:[+-]\d\d:\d\d)?$)", r"\1", raw)
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)



def redact_secret(value: Any, secret: str = "") -> str:
    text = compact(value, 500)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"https://(?:www\.)?ua\.jooble\.org/api/[^\s/?#]+", "https://ua.jooble.org/api/[REDACTED]", text, flags=re.IGNORECASE)
    return text

def validate_link(value: Any) -> str:
    link = compact(value, 2000)
    try:
        parts = urlsplit(link)
    except ValueError:
        return ""
    if parts.scheme != "https" or (parts.hostname or "").lower() not in ALLOWED_HOSTS:
        return ""
    return link


def canonical_jdp(link: str) -> str | None:
    match = JDP_RE.search(link)
    return match.group(1) if match else None


def normalize_api_job(raw: dict[str, Any], query_id: str) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    api_id = compact(raw.get("id"), 120)
    title = compact(raw.get("title"), 240)
    link = validate_link(raw.get("link"))
    if not api_id or not title or not link:
        return None
    jdp_id = canonical_jdp(link)
    updated_raw = compact(raw.get("updated"), 120)
    updated_dt = parse_iso_timestamp(updated_raw)
    return {
        "identity": f"jdp:{jdp_id}" if jdp_id else f"api:{api_id}",
        "api_id": api_id,
        "jdp_id": jdp_id,
        "title": title,
        "company": compact(raw.get("company"), 240) or "не вказано",
        "location": compact(raw.get("location"), 500),
        "snippet": compact(raw.get("snippet"), 8_000),
        "salary": compact(raw.get("salary"), 240),
        "source_name": compact(raw.get("source"), 240),
        "employment_type": compact(raw.get("type"), 240),
        "link": link,
        "updated": updated_raw,
        "updated_dt": updated_dt,
        "query_ids": {query_id},
    }


def merge_job(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["query_ids"] = set(existing.get("query_ids", set())) | set(incoming.get("query_ids", set()))
    for field in ("snippet", "location", "company", "salary", "source_name", "employment_type"):
        if len(str(incoming.get(field, ""))) > len(str(merged.get(field, ""))):
            merged[field] = incoming[field]
    incoming_dt, existing_dt = incoming.get("updated_dt"), merged.get("updated_dt")
    if incoming_dt and (not existing_dt or incoming_dt > existing_dt):
        merged["updated_dt"] = incoming_dt
        merged["updated"] = incoming.get("updated", "")
    return merged


def request_payload(config: dict[str, Any], query: Query, page: int = 1) -> dict[str, Any]:
    return {
        "keywords": query.keywords,
        "location": query.location,
        "page": page,
        "ResultOnPage": config["result_on_page"],
        "SearchMode": config["search_mode"],
        "companysearch": config["companysearch"],
    }


def perform_request(api_key: str, config: dict[str, Any], query: Query) -> ApiResponse:
    reserve_request_slot()
    endpoint = "https://ua.jooble.org/api/" + api_key
    body = json.dumps(request_payload(config, query), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "RADAR-JOOBLE/2"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", response.getcode()))
            if status != 200:
                raise ApiRunnerError(f"Jooble API returned HTTP {status}")
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_RESPONSE_BYTES:
                raise ApiRunnerError("Jooble API response exceeds safety limit")
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise ApiRunnerError("Jooble API response exceeds safety limit")
    except HTTPError as exc:
        raise ApiRunnerError(f"Jooble API returned HTTP {exc.code}") from None
    except URLError as exc:
        reason = redact_secret(getattr(exc, "reason", "network error"), api_key)[:160]
        raise ApiRunnerError(f"Jooble API network error: {reason}") from None
    except TimeoutError:
        raise ApiRunnerError("Jooble API request timed out") from None
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiRunnerError("Jooble API returned invalid JSON") from exc
    if not isinstance(decoded, dict) or not isinstance(decoded.get("jobs"), list):
        raise ApiRunnerError("Jooble API response schema is invalid")
    total = decoded.get("totalCount", len(decoded["jobs"]))
    if isinstance(total, bool) or not isinstance(total, int) or total < 0:
        raise ApiRunnerError("Jooble API totalCount is invalid")
    mark_request_success()
    return ApiResponse(query=query, total_count=total, jobs=decoded["jobs"])


def load_fixture(path: Path, query: Query) -> ApiResponse:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiRunnerError("fixture is missing or invalid") from exc
    if not isinstance(decoded, dict):
        raise ApiRunnerError("fixture schema is invalid")
    by_query = decoded.get("queries")
    if isinstance(by_query, dict) and query.query_id in by_query:
        decoded = by_query[query.query_id]
    if not isinstance(decoded, dict) or not isinstance(decoded.get("jobs"), list):
        raise ApiRunnerError(f"fixture has no jobs for {query.query_id}")
    total = decoded.get("totalCount", len(decoded["jobs"]))
    if isinstance(total, bool) or not isinstance(total, int):
        total = len(decoded["jobs"])
    return ApiResponse(query=query, total_count=total, jobs=decoded["jobs"])


def classify_api_job(job: dict[str, Any], *, freshness_unknown: bool = False) -> dict[str, Any]:
    title, company, location, snippet = job["title"], job["company"], job["location"], job["snippet"]
    card = {"title": title, "listing_text": snippet, "location_text": location}
    rule = radar.safe_listing_reject(card)
    facts = radar.derive_detail_facts(radar.SOURCE, title, location, snippet)
    if not rule:
        rule = facts["reject_rule"]
    target_text = f"{title}\n{snippet}"
    target_evidence = bool(
        radar.POSITIVE_WEB.search(target_text)
        or (radar.AI_TOOLING.search(target_text) and radar.JS_WEB.search(target_text))
    )
    if not rule and not target_evidence:
        rule = "NOT_TARGET_WEB_JS"
    primary_title_target = bool(radar.JS_WEB_LANE.search(title) or radar.AI_ROLE_TITLE.search(title))
    review: list[str] = []
    if not rule and target_evidence and not primary_title_target:
        review.append("Primary target role is not confirmed by title")
    junior_frontend = bool(radar.JUNIOR.search(title) and radar.FRONTEND_LANE.search(title) and not radar.FULLSTACK_LANE.search(title))
    mixed_level = bool(re.search(r"\bjunior\s*(?:/|[-–])\s*(?:middle|senior)\b", title, re.IGNORECASE))
    if junior_frontend and not mixed_level and not rule:
        rule = "FRONTEND_LEVEL_TOO_LOW"

    work_mode = facts["work_mode"]
    combined = f"{location}\n{snippet}\n{title}"
    if HYBRID_RE.search(combined):
        work_mode = "HYBRID"
    elif REMOTE_RE.search(combined):
        work_mode = "REMOTE"
    elif OFFICE_RE.search(combined):
        work_mode = "OFFICE"
    if not rule and work_mode == "OFFICE":
        rule = "NON_REMOTE_OFFICE"
    elif not rule and work_mode == "UNKNOWN":
        review.append("Remote/hybrid format is not explicitly confirmed by API listing evidence")
    # HYBRID is intentionally eligible: preserved browser behavior and user target lane.

    if facts["review_reason"] and not rule:
        review.append(facts["review_reason"])
    if freshness_unknown and not rule:
        review.append("API updated timestamp is missing/invalid; freshness is not proven")
    if company == "не вказано" and not rule:
        review.append("Company is not provided by API")

    if rule:
        decision, caution = "REJECT", rule
    elif review:
        decision, caution = "REVIEW", "; ".join(dict.fromkeys(review))
    else:
        decision, caution = "MATCH", ""
    evidence = "API title/location/snippet evidence; full vacancy detail was not opened"
    caution = f"{caution}; {evidence}" if caution else evidence
    city = facts["city"]
    if work_mode in {"HYBRID", "OFFICE"} and not city:
        city = "не вказано"
    return {
        "identity": job["identity"],
        "api_id": job["api_id"],
        "jdp_id": job.get("jdp_id"),
        "url": job["link"],
        "source": radar.SOURCE,
        "transport": "API",
        "title": title,
        "company": company,
        "updated_at": job["updated"] or None,
        "published_date": None,
        "decision": decision,
        "work_mode": work_mode,
        "city": city,
        "reservation": facts["reservation"],
        "caution": caution,
        "salary": job["salary"],
        "employment_type": job["employment_type"],
        "api_source": job["source_name"],
        "location_text": location,
        "query_ids": sorted(job["query_ids"]),
        "rule": rule,
    }


def read_seen() -> dict[str, dict[str, Any]]:
    if not SEEN_PATH.exists():
        return {}
    found: dict[str, dict[str, Any]] = {}
    try:
        for line in SEEN_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if isinstance(item, dict) and isinstance(item.get("identity"), str):
                found[item["identity"]] = item
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiRunnerError("state/api-seen.jsonl is invalid") from exc
    return found


def seen_item_unchanged(item: dict[str, Any], previous: dict[str, Any] | None) -> bool:
    if not previous or previous.get("ruleset") != API_RULESET_VERSION:
        return False
    return previous.get("updated_at") == item.get("updated_at") and previous.get("decision") == item.get("decision")


def persist_seen(items: list[dict[str, Any]], run_id: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    previous = read_seen()
    now_iso = utc_now().isoformat()
    for item in items:
        previous[item["identity"]] = {
            "identity": item["identity"],
            "url": item["url"],
            "ruleset": API_RULESET_VERSION,
            "updated_at": item.get("updated_at"),
            "decision": item["decision"],
            "seen_at": now_iso,
            "run_id": run_id,
        }
    fd, tmp = tempfile.mkstemp(prefix=".api-seen.", suffix=".tmp", dir=STATE_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for identity in sorted(previous):
                handle.write(json.dumps(previous[identity], ensure_ascii=False, separators=(",", ":")) + "\n")
            handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, SEEN_PATH)
    finally:
        try: os.unlink(tmp)
        except FileNotFoundError: pass


def choose_freshness(explicit: str | None, *, test_live: bool) -> tuple[str, bool]:
    if explicit:
        return explicit, False
    if test_live:
        return "3d", False
    watermark = read_json(WATERMARK_PATH, {}) if WATERMARK_PATH.exists() else {}
    last = parse_iso_timestamp(watermark.get("finished_at"))
    if not last:
        return "3d", False
    gap = utc_now() - last
    if gap <= timedelta(days=2):
        return "3d", False
    if gap <= timedelta(days=6):
        return "7d", False
    return "7d", True


def result_stem(started: datetime, finished: datetime, *, test_live: bool) -> str:
    left = started.astimezone(radar.KYIV).strftime("%d.%m.%Y %H.%M")
    right = finished.astimezone(radar.KYIV).strftime("%d.%m.%Y %H.%M")
    launch = started.astimezone(radar.KYIV).strftime("%d.%m.%Y %H.%M.%S")
    prefix = "Тест API вакансій" if test_live else "Вакансії"
    return f"{prefix} {left} — {right} · запуск {launch}"


def unique_paths(directory: Path, stem: str) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    RUN_DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = ""
    n = 1
    while True:
        candidate = stem + suffix
        md = directory / f"{candidate}.md"
        js = directory / f"{candidate}.jsonl"
        diag = RUN_DIAGNOSTICS_DIR / f"{candidate}.diagnostics.json"
        if not md.exists() and not js.exists() and not diag.exists():
            return md, js, diag
        n += 1; suffix = f" ({n})"


def write_results(*, started: datetime, finished: datetime, freshness_key: str, cutoff: datetime,
                  test_live: bool, status: str, coverage_mode: str, gap_risk: bool,
                  request_rows: list[dict[str, Any]], all_unique: int, recent_unique: int,
                  stale_count: int, unknown_updated: int, classified_all: list[dict[str, Any]],
                  visible_items: list[dict[str, Any]], suppressed_seen: int,
                  stopped_reason: str) -> tuple[Path, Path, Path]:
    directory = TEST_RESULTS_DIR if test_live else RESULTS_DIR
    md_path, jsonl_path, diag_path = unique_paths(directory, result_stem(started, finished, test_live=test_live))
    output_items = [item for item in visible_items if item["decision"] in {"MATCH", "REVIEW"}]
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for item in output_items:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush(); os.fsync(handle.fileno())
    counts_all = {d: sum(i["decision"] == d for i in classified_all) for d in ("MATCH", "REVIEW", "REJECT")}
    counts_visible = {d: sum(i["decision"] == d for i in visible_items) for d in ("MATCH", "REVIEW", "REJECT")}
    diagnostics = {
        "schema_version": API_SCHEMA_VERSION,
        "ruleset_version": API_RULESET_VERSION,
        "transport": "Jooble REST API",
        "status": status,
        "coverage_mode": coverage_mode,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "freshness": {"key": freshness_key, "cutoff_utc": cutoff.isoformat(), "semantic": "API updated timestamp, not publication date"},
        "coverage_gap_risk": gap_risk,
        "requests": request_rows,
        "all_unique_jobs": all_unique,
        "recent_unique_jobs": recent_unique,
        "stale_jobs": stale_count,
        "unknown_updated_jobs": unknown_updated,
        "suppressed_seen": suppressed_seen,
        "visible_counts": counts_visible,
        "all_recent_counts": counts_all,
        "stopped_reason": stopped_reason or None,
        "quota": read_json(USAGE_PATH, {"attempted": 0, "successful": 0, "quota": API_QUOTA_LIFETIME}),
    }
    atomic_write_json(diag_path, diagnostics)

    lines = [
        f"# {md_path.stem}", "",
        f"Статус: **{status}**", "",
        f"Джерело: **Jooble REST API** · coverage: **{coverage_mode}** · freshness: **{freshness_key}** по `updated` (не publication date).",
        f"API unique: **{all_unique}** · у freshness-вікні: **{recent_unique}** · приховано як already-seen: **{suppressed_seen}**.",
    ]
    if stopped_reason:
        lines += ["", f"> Blocker: {stopped_reason}"]
    if gap_risk:
        lines += ["", "> Увага: normal gap >6 днів; 7d `updated` window не доводить gap-free coverage."]
    if coverage_mode == "BOUNDED_PAGE1":
        lines += ["", "> Coverage bounded: принаймні один query має `totalCount` > page-1 response; API quota-aware normal run не заявляє exhaustive coverage."]
    lines += ["", "| Query | HTTP | totalCount | returned |", "|---|---:|---:|---:|"]
    for row in request_rows:
        lines.append(f"| {row['id']} | {row.get('http_status', '—')} | {row.get('total_count', '—')} | {row.get('returned', 0)} |")
    sections = (
        ("Бронювання підтверджено", [i for i in output_items if i["reservation"] == "CONFIRMED"]),
        ("Підходять", [i for i in output_items if i["reservation"] != "CONFIRMED" and i["decision"] == "MATCH"]),
        ("Потрібно перевірити", [i for i in output_items if i["reservation"] != "CONFIRMED" and i["decision"] == "REVIEW"]),
    )
    for heading, values in sections:
        lines += ["", f"## {heading}", ""]
        values.sort(key=lambda i: (i.get("updated_at") or "", i["title"].casefold()), reverse=True)
        if not values:
            lines.append("—"); continue
        for item in values:
            place = " / ".join(v for v in (item.get("work_mode"), item.get("city")) if v) or "UNKNOWN"
            updated = item.get("updated_at") or "updated невідомо"
            lines.append(f"- [{item['title']}]({item['url']}) — {item['company']} · {updated} · {place}")
            if item.get("salary"):
                lines.append(f"  - Зарплата: {item['salary']}")
            if item.get("caution"):
                lines.append(f"  - Увага: {item['caution']}")
    lines += ["", f"Відхилено внутрішнім фільтром (не показані списком): **{counts_visible['REJECT']}**", ""]
    atomic_write_text(md_path, "\n".join(lines).rstrip() + "\n")
    return md_path, jsonl_path, diag_path


def ensure_no_secret_leak(paths: Iterable[Path], secret: str) -> None:
    if not secret:
        return
    bad = False
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if secret in content or "JOOBLE_API_KEY=" in content:
            bad = True; break
    if bad:
        for path in paths:
            try: path.unlink()
            except OSError: pass
        raise ApiRunnerError("SECRET_LEAK_PREVENTED")


def recent_normal_result() -> dict[str, Any] | None:
    if not WATERMARK_PATH.exists():
        return None
    watermark = read_json(WATERMARK_PATH, {})
    if watermark.get("status") != "DONE":
        return None
    finished = parse_iso_timestamp(watermark.get("finished_at"))
    if not finished or utc_now() - finished >= MIN_NORMAL_INTERVAL:
        return None
    md, js = str(watermark.get("markdown", "")), str(watermark.get("jsonl", ""))
    if not md or not js or not Path(md).exists() or not Path(js).exists():
        return None
    return {
        "status": "NOOP_RECENT",
        "transport": "API",
        "requests_used": 0,
        "counts": watermark.get("counts", {}),
        "coverage_mode": watermark.get("coverage_mode"),
        "freshness": watermark.get("freshness"),
        "markdown": md,
        "jsonl": js,
        "reused_recent_normal_result": True,
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    config = load_config()
    if not args.test_live and not args.force and not args.fixture:
        recent = recent_normal_result()
        if recent is not None:
            return recent
    queries: list[Query] = config["queries"]
    limit = args.max_requests if args.max_requests is not None else len(queries)
    if limit < 1 or limit > len(queries):
        raise ApiRunnerError(f"--max-requests must be in 1..{len(queries)}")
    freshness_key, gap_risk = choose_freshness(args.freshness, test_live=args.test_live)
    started = utc_now(); cutoff = started - FRESHNESS[freshness_key]
    fixture = Path(args.fixture).resolve() if args.fixture else None
    api_key = "" if fixture else load_api_key()

    responses: list[ApiResponse] = []
    request_rows: list[dict[str, Any]] = []
    stopped_reason = ""
    for query in queries[:limit]:
        try:
            response = load_fixture(fixture, query) if fixture else perform_request(api_key, config, query)
        except ApiRunnerError as exc:
            stopped_reason = str(exc)
            request_rows.append({"id": query.query_id, "http_status": "ERROR", "returned": 0, "error": stopped_reason})
            break
        responses.append(response)
        request_rows.append({
            "id": query.query_id,
            "http_status": 200,
            "total_count": response.total_count,
            "returned": len(response.jobs),
            "truncated": response.total_count > len(response.jobs),
        })

    merged: dict[str, dict[str, Any]] = {}; invalid_jobs = 0
    for response in responses:
        for raw in response.jobs:
            job = normalize_api_job(raw, response.query.query_id)
            if job is None:
                invalid_jobs += 1; continue
            merged[job["identity"]] = merge_job(merged[job["identity"]], job) if job["identity"] in merged else job

    recent_jobs: list[tuple[dict[str, Any], bool]] = []
    stale_count = unknown_updated = 0
    for job in merged.values():
        updated = job.get("updated_dt")
        if updated is None:
            unknown_updated += 1
            recent_jobs.append((job, True))
        elif updated < cutoff:
            stale_count += 1
        else:
            recent_jobs.append((job, False))
    classified_all = [classify_api_job(job, freshness_unknown=unknown) for job, unknown in recent_jobs]
    classified_all.sort(key=lambda i: (i["decision"] != "MATCH", i["decision"] != "REVIEW", i["title"].casefold(), i["identity"]))
    seen = {} if args.test_live or fixture else read_seen()
    visible_items = classified_all if args.test_live or fixture else [i for i in classified_all if not seen_item_unchanged(i, seen.get(i["identity"]))]
    suppressed_seen = len(classified_all) - len(visible_items)

    if not responses:
        status = "BLOCKED"
    elif stopped_reason or len(responses) < limit:
        status = "PARTIAL"
    else:
        status = "DONE"
    coverage_mode = "NONE" if not responses else ("BOUNDED_PAGE1" if any(r.get("truncated") for r in request_rows) else "PAGE1_COMPLETE")
    finished = utc_now()
    md_path, js_path, diag_path = write_results(
        started=started, finished=finished, freshness_key=freshness_key, cutoff=cutoff,
        test_live=args.test_live, status=status, coverage_mode=coverage_mode, gap_risk=gap_risk,
        request_rows=request_rows, all_unique=len(merged), recent_unique=len(recent_jobs),
        stale_count=stale_count, unknown_updated=unknown_updated, classified_all=classified_all,
        visible_items=visible_items, suppressed_seen=suppressed_seen, stopped_reason=stopped_reason,
    )
    ensure_no_secret_leak((md_path, js_path, diag_path), api_key)
    counts = {d: sum(i["decision"] == d for i in visible_items) for d in ("MATCH", "REVIEW", "REJECT")}
    if not args.test_live and not fixture and responses:
        persist_seen(classified_all, md_path.stem)
    if not args.test_live and not fixture and status == "DONE":
        atomic_write_json(WATERMARK_PATH, {
            "schema_version": 2,
            "finished_at": finished.isoformat(),
            "status": status,
            "coverage_mode": coverage_mode,
            "freshness": freshness_key,
            "api_unique_jobs": len(merged),
            "recent_unique_jobs": len(recent_jobs),
            "counts": counts,
            "markdown": str(md_path),
            "jsonl": str(js_path),
        })
    return {
        "status": status,
        "transport": "API",
        "coverage_mode": coverage_mode,
        "freshness": freshness_key,
        "requests_used": len(responses),
        "request_attempts_this_run": len(request_rows),
        "api_unique_jobs": len(merged),
        "recent_unique_jobs": len(recent_jobs),
        "invalid_jobs": invalid_jobs,
        "suppressed_seen": suppressed_seen,
        "counts": counts,
        "markdown": str(md_path),
        "jsonl": str(js_path),
        "stopped_reason": stopped_reason or None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="run", choices=("run",))
    parser.add_argument("--test-live", action="store_true", help="isolated output; does not update API seen/watermark")
    parser.add_argument("--freshness", choices=tuple(FRESHNESS), default=None)
    parser.add_argument("--max-requests", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="bypass recent-result reuse; consumes quota")
    parser.add_argument("--fixture", default=None, help=argparse.SUPPRESS)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        with exclusive_run_lock():
            result = execute(args)
    except ApiRunnerError as exc:
        print(json.dumps({"status": "BLOCKED", "transport": "API", "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
