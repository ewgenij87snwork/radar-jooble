#!/usr/bin/env python3
"""Standalone state and result writer for browser-driven RADAR-JOOBLE."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, unquote_plus, urlsplit, urlunsplit
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
TEST_RESULTS = RESULTS / "test"
SOURCE = "Jooble"
SOURCES = (SOURCE,)
SOURCE_FILES = {SOURCE: "jooble.md"}
SOURCE_ROUTES = {
    SOURCE: (
        "angular developer",
        "react developer",
        "frontend developer",
        "front end developer",
        "frontend engineer",
        "typescript developer",
        "javascript developer",
        "full stack developer",
        "fullstack engineer",
        "node.js developer",
        "nestjs developer",
        "ai developer",
        "ai engineer",
    )
}
SOURCE_DATE_ZONES = {SOURCE: "Europe/Kyiv"}
SOURCE_HOSTS = {SOURCE: {"ua.jooble.org", "www.ua.jooble.org"}}
VACANCY_PATHS = {SOURCE: re.compile(r"^/jdp/-?\d+(?:[-/]|$)")}
JOOBLE_REMOTE_PATHS = {"віддалено", "удаленно", "remote"}
MAX_RUNS = 60
KYIV = ZoneInfo("Europe/Kyiv")
TRACKING = {
    "ref", "sid", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "clickid", "source",
}
OBSERVATION_VERSION = 7
COVERAGE_VERSION = "JOOBLE_REMOTE_FRESHNESS_V7"
RULESET_VERSION = "2026-09-21.3"
TERMINALS = {"NO_NEXT", "NO_NEW_URLS"}
SOURCE_SORTS = {SOURCE: "jooble-freshness-exhaustive"}
EXCLUDABLE_SOURCES = frozenset()
FRESHNESS = {
    "24h": {"param": "8", "days": 1},
    "3d": {"param": "2", "days": 3},
    "7d": {"param": "3", "days": 7},
}
STATE_DIR = ROOT / "state"
SEEN_PATH = STATE_DIR / "seen.jsonl"
POSITIVE_WEB = re.compile(
    r"\b(angular|front[ -]?end|java\s*script|type\s*script|react|next(?:\.js|js)?|vue|"
    r"full[ -]?stack|node(?:\.js|js)?|nest(?:\.js|js)?|web developer|web engineer|"
    r"ui developer|ui engineer|webmaster|(?:js|ts) (?:developer|engineer))\b",
    re.IGNORECASE,
)
AI_TOOLING = re.compile(r"\b(ai|llm|devtools?|developer tools?|tooling|agentic)\b", re.IGNORECASE)
JS_WEB = re.compile(r"\b(java\s*script|type\s*script|web|front[ -]?end|node(?:\.js|js)?|angular|react|vue|nest(?:\.js|js)?)\b", re.IGNORECASE)
JUNIOR = re.compile(r"\b(junior|jr\.?|молодш(?:ий|а)|початків(?:ець|иця))\b", re.IGNORECASE)
FRONTEND_LANE = re.compile(r"\b(front[ -]?end|angular|react|vue|ui developer|ui engineer)\b", re.IGNORECASE)
FULLSTACK_LANE = re.compile(r"\bfull[ -]?stack\b", re.IGNORECASE)
SENIOR = re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE)
PLACEHOLDERS = {"unknown", "n/a", "na", "невідомо", "невідомий", "не вказано", "не указано"}
DETAIL_FIELDS = {"url", "final_url", "title", "company", "published_date", "location_text", "detail_text"}
LOCATION_TEXT_LIMIT = 500
DETAIL_TEXT_LIMIT = 20_000
LEADERSHIP_TITLE = re.compile(r"\b(?:head|lead|manager)\b", re.IGNORECASE)
ENTRY_TITLE = re.compile(r"\b(?:intern|trainee|graduate)\b", re.IGNORECASE)
NON_TARGET_TITLE = re.compile(
    r"\b(?:qa|quality assurance|quality analyst|data quality|business analyst|mobile|ios|android|"
    r"devops|sre|data engineer|product manager|technical artist|game developer|unity developer|embedded software)\b",
    re.IGNORECASE,
)
NON_JS_TITLE = re.compile(
    r"(?:\.net\b|\b(?:php|java(?!script)|ruby|golang|go developer|python)\b|c\+\+|c#)",
    re.IGNORECASE,
)
JS_WEB_LANE = re.compile(r"\b(?:java\s*script|type\s*script|node(?:\.js|js)?|nest(?:\.js|js)?|front[ -]?end|angular|react|vue|web)\b", re.IGNORECASE)
AI_ROLE_TITLE = re.compile(
    r"(?:\b(?:ai|ml|llm|agentic)(?:[- /][\w+#.]+){0,3}\s+(?:engineer|developer|specialist)\b|"
    r"\b(?:engineer|developer|specialist)\b.{0,24}\b(?:ai|ml|llm|agentic)\b)",
    re.IGNORECASE,
)
NODE_NEST_TITLE = re.compile(r"\b(?:node(?:\.js|js)?|nest(?:\.js|js)?)\b", re.IGNORECASE)
CORE_WEB_TITLE = re.compile(r"\b(?:front[ -]?end|angular|react|vue|type\s*script|java\s*script|full[ -]?stack|web)\b", re.IGNORECASE)
REQUIRED_WORD = r"(?:must|required|mandatory|обов['’]язково|необхідно|потрібно)"
EXPERIENCE_OVER_FIVE = re.compile(
    r"(?:\b(?:[6-9]|[1-9]\d)\s*\+\s*(?:years?|yrs?|рок(?:ів|и)?|лет)\b|"
    r"\b(?:at\s+least|minimum|min\.?|від|щонайменше)\s+(?:[6-9]|[1-9]\d)\s*"
    r"(?:years?|yrs?|рок(?:ів|и)?|лет)\b|"
    r"\b(?:[6-9]|[1-9]\d)\s*(?:-|–|to)\s*\d+\s*(?:years?|yrs?|рок(?:ів|и)?|лет)\b|"
    r"\bmore\s+than\s+five\s+years\b)", re.IGNORECASE,
)
FRONTEND_DOMINANT = re.compile(
    r"(?:front[ -]?end\s*[- ]?focused|mostly\s+front[ -]?end|(?:70|80|90|100)\s*%\s*front[ -]?end|"
    r"переважно\s+фронтенд|фронтенд\s*[- ]?орієнтован)", re.IGNORECASE,
)
UKRAINIAN_MONTHS = {
    "січня": 1, "лютого": 2, "березня": 3, "квітня": 4, "травня": 5, "червня": 6,
    "липня": 7, "серпня": 8, "вересня": 9, "жовтня": 10, "листопада": 11, "грудня": 12,
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
UKRAINIAN_DATE = re.compile(
    rf"(?<!\d)(\d{{1,2}})\s+({'|'.join(map(re.escape, UKRAINIAN_MONTHS))})(?:\s+(\d{{4}}))?(?:\s|$)",
    re.IGNORECASE,
)
RELATIVE_DATE = re.compile(
    r"(?P<n>\d+)\s*(?P<u>хв(?:илин\w*)?|мин(?:ут\w*)?|minutes?|год(?:ин\w*)?|час(?:а|ов)?|hours?|"
    r"дн(?:і|я|ів)?|день|дня|дней|days?|тиж(?:день|ні|нів)?|недел(?:ю|и|ь)|weeks?|"
    r"міс(?:яць|яці|яців)?|месяц(?:а|ев)?|months?)\s*(?:тому|назад|ago)?",
    re.IGNORECASE,
)

def now() -> datetime:
    return datetime.now(KYIV).replace(microsecond=0)


def iso(value: datetime) -> str:
    return value.isoformat()


def parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(KYIV) if parsed.tzinfo else parsed.replace(tzinfo=KYIV)


def source_reference_days(meta: dict) -> dict[str, str]:
    """Calendar day that gives yearless source dates their year."""
    started = parse_time(meta["started_at"])
    return {
        source: started.astimezone(ZoneInfo(meta["sources"][source]["date_zone"])).date().isoformat()
        for source in SOURCES
    }


def receipt_json(raw: str, label: str) -> object:
    payload = sys.stdin.read() if raw == "-" else raw
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid {label} JSON: {exc}") from exc


def read_meta(path: Path) -> dict | None:
    try:
        line = path.open(encoding="utf-8").readline().strip()
        if line.startswith("<!-- RADAR_JOOBLE ") and line.endswith(" -->"):
            return json.loads(line[len("<!-- RADAR_JOOBLE ") : -len(" -->")])
    except (OSError, json.JSONDecodeError):
        pass
    return None


def runs(directory: Path = RESULTS) -> list[tuple[Path, dict]]:
    found = []
    for path in directory.glob("*.md"):
        meta = read_meta(path)
        if meta:
            found.append((path, meta))
    return sorted(found, key=lambda item: item[1].get("started_at", ""))


def active_run() -> tuple[Path, dict] | None:
    active = [
        item
        for directory in (RESULTS, TEST_RESULTS)
        for item in runs(directory)
        if item[1].get("status") == "IN_PROGRESS"
    ]
    if len(active) > 1:
        raise SystemExit(f"Multiple active runs found: {[str(item[0]) for item in active]}")
    return active[0] if active else None


def result_name(started: datetime, ended: datetime) -> str:
    left = started.strftime("%d.%m.%Y %H.%M")
    right = ended.strftime("%d.%m.%Y %H.%M")
    return f"Вакансії {left} — {right}"


def test_result_name(started: datetime, ended: datetime, launched: datetime) -> str:
    left = started.strftime("%d.%m.%Y %H.%M")
    right = ended.strftime("%d.%m.%Y %H.%M")
    launch = launched.strftime("%d.%m.%Y %H.%M.%S")
    return f"Тест вакансій {left} — {right} · запуск {launch}"


def unused_test_path(directory: Path, stem: str) -> Path:
    path = directory / f"{stem}.md"
    sequence = 2
    while path.exists() or jsonl_for(path).exists():
        path = directory / f"{stem} ({sequence}).md"
        sequence += 1
    return path


def unused_result_path(directory: Path, stem: str) -> Path:
    path = directory / f"{stem}.md"
    sequence = 2
    while path.exists() or jsonl_for(path).exists():
        path = directory / f"{stem} ({sequence}).md"
        sequence += 1
    return path


def display_until(meta: dict) -> datetime:
    return parse_time(meta["until"])


def jsonl_for(md_path: Path) -> Path:
    return md_path.with_suffix(".jsonl")


def diagnostics_for(md_path: Path) -> Path:
    return md_path.with_name(f"{md_path.stem}.diagnostics.jsonl")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_diagnostic(md_path: Path, event: str, payload: dict) -> None:
    target = diagnostics_for(md_path)
    record = {"at": iso(now()), "event": event, **payload}
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        pass


def read_seen_entries() -> dict[str, dict]:
    entries: dict[str, dict] = {}
    if not SEEN_PATH.exists():
        return entries
    for item in read_items(SEEN_PATH):
        url = item.get("url")
        if isinstance(url, str):
            entries[canonical_url(url)] = item
    return entries


def current_seen_urls() -> set[str]:
    return {
        url for url, item in read_seen_entries().items()
        if item.get("ruleset") == RULESET_VERSION
    }


def persist_seen(outcomes: list[dict], run_id: str) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entries = read_seen_entries()
    stamped = iso(now())
    for item in outcomes:
        url = canonical_url(item["url"])
        previous = entries.get(url, {})
        entries[url] = {
            "url": url,
            "ruleset": RULESET_VERSION,
            "first_seen": previous.get("first_seen", stamped),
            "last_seen": stamped,
            "run": run_id,
            "result": item.get("result", ""),
            "rule": item.get("rule", ""),
            "title": item.get("title", ""),
            "company": item.get("company", ""),
        }
    temp = SEEN_PATH.with_suffix(".jsonl.tmp")
    with temp.open("w", encoding="utf-8") as handle:
        for url in sorted(entries):
            handle.write(json.dumps(entries[url], ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, SEEN_PATH)


def read_items(path: Path) -> list[dict]:
    items = []
    if not path.exists():
        return items
    with path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, 1):
            if line.strip():
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise SystemExit(f"Invalid JSONL at {path.name}:{number}: {exc}")
    return items


def canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise SystemExit("URL must be an absolute http(s) URL")
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in TRACKING and not key.lower().startswith("utm_")
    ]
    path = re.sub(r"/{2,}", "/", parts.path)
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path or "/", urlencode(sorted(query)), ""))


def source_url(source: str, value: str, *, vacancy: bool = False) -> str:
    url = canonical_url(value)
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host not in SOURCE_HOSTS[source]:
        raise SystemExit(f"URL does not belong to {source}: {url}")
    if vacancy and not VACANCY_PATHS[source].search(parts.path):
        raise SystemExit(f"URL is not a direct {source} vacancy: {url}")
    return url


def query_map(url: str) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
        values.setdefault(key, []).append(value)
    return values


def compact(value: str) -> str:
    return re.sub(r"[^a-zа-яіїєґ0-9]+", "", unquote_plus(value).casefold())


def route_url(source: str, name: str, value: str, *, freshness_param: str | None = None) -> str:
    url = source_url(source, value)
    parts = urlsplit(url)
    path = unquote_plus(parts.path).casefold().rstrip("/")
    if source != SOURCE:
        raise SystemExit(f"Unsupported source: {source}")
    segments = [segment for segment in path.split("/") if segment]
    remote_segments = [segment for segment in segments if segment in JOOBLE_REMOTE_PATHS]
    if not remote_segments:
        raise SystemExit(f"Jooble route {name} must preserve Remote location path; legacy l=Remote is not accepted: {url}")
    if query_map(url).get("l"):
        raise SystemExit(f"Jooble route {name} rejects legacy l=Remote query proof: {url}")
    prefix = next((item for item in ("робота-", "работа-") if any(segment.startswith(item) for segment in segments)), None)
    if prefix is None:
        raise SystemExit(f"URL does not preserve Jooble search route {name}: {url}")
    slug = compact(next(segment for segment in segments if segment.startswith(prefix)).removeprefix(prefix))
    requested = compact(name)
    if requested not in slug and slug not in requested:
        raise SystemExit(f"URL does not preserve route {name} for Jooble: {url}")
    if freshness_param is not None:
        values = query_map(url).get("date", [])
        if values != [freshness_param]:
            raise SystemExit(
                f"Jooble route {name} must preserve freshness date={freshness_param}; received={values or 'missing'}"
            )
    return url


def known_urls_for(
    run_path: Path,
    *,
    except_path: Path | None = None,
    current_source: str | None = None,
) -> set[str]:
    known = set()
    current_jsonl = jsonl_for(run_path)
    if run_path.parent != TEST_RESULTS:
        known.update(current_seen_urls())
        paths = list(RESULTS.glob("*.jsonl"))
    else:
        paths = [current_jsonl]
    for path in paths:
        if path == except_path:
            continue
        for item in read_items(path):
            if current_source is not None and path == current_jsonl and item.get("source") == current_source:
                continue
            if item.get("url"):
                known.add(canonical_url(item["url"]))
    return known


def required_queries(source: str) -> list[str]:
    return list(SOURCE_ROUTES[source])


def empty_observations() -> dict:
    return {"version": OBSERVATION_VERSION, "sort": "", "routes": {}}


def observation_progress(source: str, state: dict) -> tuple[dict, list[str], list[str], str | None]:
    observations = state.get("observations")
    expected_fields = {"version", "sort", "routes"}
    if not isinstance(observations, dict) or set(observations) != expected_fields:
        raise SystemExit(f"{source} observations fields must be exactly {sorted(expected_fields)}")
    if observations["version"] != OBSERVATION_VERSION:
        raise SystemExit(f"{source} observations version must be exactly {OBSERVATION_VERSION}")
    routes = observations["routes"]
    if not isinstance(routes, dict):
        raise SystemExit(f"{source} observation routes must be a dict")
    required = required_queries(source)
    completed = list(routes)
    if completed != required[: len(completed)]:
        raise SystemExit(f"{source} observed route keys must be the required prefix {required}; received={completed}")
    expected_sort = SOURCE_SORTS[source] if completed else ""
    if observations["sort"] != expected_sort:
        raise SystemExit(f"{source} observation sort must be exactly {expected_sort!r}")
    next_route = required[len(completed)] if len(completed) < len(required) else None
    return observations, required, completed, next_route


def next_source(meta: dict) -> str | None:
    return next((source for source in SOURCES if meta["sources"][source].get("status") == "PENDING"), None)


def require_current_source(meta: dict, source: str, action: str) -> dict:
    current = next_source(meta)
    if current is None:
        raise SystemExit(f"No source is pending; call finish instead of {action}")
    if source != current:
        raise SystemExit(f"{action} must process next_source {current}, not {source}")
    return meta["sources"][source]


def normalize_publication(value: str, *, reference_day: date | None = None) -> str | None:
    raw = re.sub(r"\s+", " ", value).strip()
    if not raw or raw.casefold() in PLACEHOLDERS:
        return None
    lowered = raw.casefold()
    if reference_day is not None:
        if lowered in {"сьогодні", "сегодня", "today"}:
            return reference_day.isoformat()
        if lowered in {"вчора", "вчера", "yesterday"}:
            return (reference_day - timedelta(days=1)).isoformat()
        relative = RELATIVE_DATE.search(lowered)
        if relative:
            amount = int(relative.group("n"))
            unit = relative.group("u").casefold()
            if re.match(r"(?:хв|мин|minute)", unit) or re.match(r"(?:год|час|hour)", unit):
                days = 0
            elif re.match(r"(?:дн|день|дня|дней|day)", unit):
                days = amount
            elif re.match(r"(?:тиж|недел|week)", unit):
                days = amount * 7
            else:
                days = amount * 30
            return (reference_day - timedelta(days=days)).isoformat()
    localized = UKRAINIAN_DATE.search(raw)
    if localized:
        day_value, month_name, year_value = localized.groups()
        try:
            if year_value is None:
                if reference_day is None:
                    raise SystemExit(f"Publication date without a year needs a frozen source window: {raw}")
                localized_day = date(reference_day.year, UKRAINIAN_MONTHS[month_name.casefold()], int(day_value))
                if localized_day > reference_day:
                    localized_day = localized_day.replace(year=localized_day.year - 1)
                return localized_day.isoformat()
            return date(int(year_value), UKRAINIAN_MONTHS[month_name.casefold()], int(day_value)).isoformat()
        except ValueError as exc:
            raise SystemExit(f"Invalid publication date: {localized.group(0).strip()}") from exc
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError as exc:
            raise SystemExit(f"Invalid publication date: {raw}") from exc
    try:
        return iso(parse_time(raw))
    except ValueError as exc:
        raise SystemExit(f"Publication date must be ISO datetime, date, Jooble relative date, or UNKNOWN: {raw}") from exc


def publication_day(value: str | None) -> date | None:
    if value is None:
        return None
    if len(value) == 10:
        return date.fromisoformat(value)
    return parse_time(value).date()


def normalize_card(raw: dict, source: str, *, reference_day: date | None = None) -> dict:
    required = {"url", "title", "company", "date", "snippet", "promoted"}
    if not isinstance(raw, dict) or not required.issubset(raw):
        raise SystemExit(f"Observed card fields must include {sorted(required)}")
    url = source_url(source, str(raw["url"]), vacancy=True)
    title = re.sub(r"\s+", " ", str(raw["title"]).strip())
    company = re.sub(r"\s+", " ", str(raw["company"]).strip())
    if not title or not company:
        raise SystemExit("Observed card requires non-empty title and company")
    raw_date = str(raw["date"]).strip()
    published = normalize_publication(raw_date, reference_day=reference_day)
    snippet = re.sub(r"\s+", " ", str(raw["snippet"]).strip())
    snippet = snippet[:240]
    if not isinstance(raw["promoted"], bool):
        raise SystemExit("Observed card promoted must be true or false")
    return {
        "url": url,
        "title": title,
        "company": company,
        "date": published,
        "snippet": snippet,
        "promoted": raw["promoted"],
        "carrier_url": source_url(source, str(raw.get("carrier_url")), vacancy=False) if raw.get("carrier_url") else "",
        "listing_text": bounded_text(str(raw.get("listing_text", snippet)), label="Listing text", limit=4000),
        "location_text": bounded_text(str(raw.get("location_text", "")), label="Listing location", limit=500),
        "origin_url": source_url(source, str(raw.get("origin_url")), vacancy=False) if raw.get("origin_url") else "",
    }


def identity_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def bounded_text(value: str, *, label: str, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) > limit:
        raise SystemExit(f"{label} exceeds {limit} characters")
    return normalized


def required_near(text_value: str, pattern: str) -> bool:
    return bool(
        re.search(rf"{REQUIRED_WORD}.{{0,100}}(?:{pattern})", text_value, re.IGNORECASE)
        or re.search(rf"(?:{pattern}).{{0,100}}{REQUIRED_WORD}", text_value, re.IGNORECASE)
    )


def location_city(location_text: str) -> str:
    for raw in re.split(r"[|,;/\n]+", location_text):
        value = re.sub(
            r"\b(?:remote|hybrid|office|віддалено|віддалений|гібрид|офіс|формат|"
            r"роботи|work|ukraine|україна)\b",
            " ",
            raw,
            flags=re.IGNORECASE,
        )
        value = re.sub(r"\s+", " ", value).strip(" -–—·")
        if value and re.search(r"[A-Za-zА-Яа-яІіЇїЄєҐґ]", value):
            return value[:80]
    return ""


def reservation_confirmed(text_value: str) -> bool:
    for sentence in re.split(r"(?<=[.!?])\s+|[\n;]", text_value):
        if not re.search(r"бронюван|бронь", sentence, re.IGNORECASE):
            continue
        if re.search(r"(?:без|не\s+надаємо|не\s+передбачено|відсутн\w*)[^.!?]{0,60}(?:бронюван|бронь)", sentence, re.IGNORECASE):
            continue
        return True
    return False


def derive_detail_facts(source: str, title: str, location_text: str, detail_text: str) -> dict:
    combined = f"{location_text}\n{detail_text}"
    lane = bool(JS_WEB_LANE.search(title))
    reject_rule = ""
    if LEADERSHIP_TITLE.search(title):
        reject_rule = "LEADERSHIP"
    elif ENTRY_TITLE.search(title):
        reject_rule = "INTERN_TRAINEE_GRADUATE"
    elif NON_TARGET_TITLE.search(title) and not lane:
        reject_rule = "NON_TARGET_SPECIALTY"
    elif NON_JS_TITLE.search(title) and not FULLSTACK_LANE.search(title):
        # Explicit Java/.NET/PHP/Python/etc primary roles are not JS/web roles merely
        # because React/Angular appears as a secondary technology in the title.
        reject_rule = "PRIMARY_NON_JS_STACK"
    elif required_near(combined, r"mentor(?:ing)?|mentoring|hiring|recruit(?:ment|ing)?|build(?:ing)?\s+(?:a\s+)?team"):
        reject_rule = "MENTORING_OR_HIRING"
    elif required_near(combined, r"pre[ -]?sales|client[ -]?(?:facing|communication|meetings?)|customer[ -]?(?:facing|communication)"):
        reject_rule = "CLIENT_HEAVY_OR_PRESALES"
    elif required_near(combined, r"travel|відряджен\w*|командировк\w*"):
        reject_rule = "MANDATORY_TRAVEL"
    elif EXPERIENCE_OVER_FIVE.search(combined):
        reject_rule = "EXPERIENCE_OVER_FIVE"

    if re.search(r"\bhybrid|гібрид", combined, re.IGNORECASE):
        work_mode = "HYBRID"
    elif re.search(r"\bremote|віддален|дистанційн", combined, re.IGNORECASE):
        work_mode = "REMOTE"
    elif re.search(r"\boffice|офіс", combined, re.IGNORECASE):
        work_mode = "OFFICE"
    else:
        work_mode = "UNKNOWN"
    city = location_city(location_text)
    senior_fullstack = bool(SENIOR.search(title) and FULLSTACK_LANE.search(title))
    frontend_heavy = bool(senior_fullstack and FRONTEND_DOMINANT.search(combined))
    review_reason = ""
    if senior_fullstack and not frontend_heavy:
        review_reason = "Senior Fullstack: frontend-домінування не підтверджено"
    return {
        "work_mode": work_mode,
        "city": city,
        "reservation": "CONFIRMED" if reservation_confirmed(combined) else "NOT_MENTIONED",
        "reject_rule": reject_rule,
        "review_reason": review_reason,
        "frontend_heavy": frontend_heavy,
    }


def observed_candidates(state: dict) -> dict[str, dict]:
    observations = state.get("observations") or {}
    routes = observations.get("routes") or {}
    candidates: dict[str, dict] = {}
    for route in routes.values():
        for page in route.get("pages", []):
            for card in page.get("cards", []):
                candidates.setdefault(card["url"], card)
    return candidates


def safe_listing_reject(card: dict) -> str:
    text = f"{card.get('title', '')}\n{card.get('listing_text', '')}\n{card.get('location_text', '')}"
    title = str(card.get("title", ""))
    if LEADERSHIP_TITLE.search(title):
        return "LISTING_LEADERSHIP_TITLE"
    if ENTRY_TITLE.search(title):
        return "LISTING_INTERN_TRAINEE"
    if NON_TARGET_TITLE.search(title):
        return "LISTING_NON_TARGET_SPECIALTY"
    if NON_JS_TITLE.search(title) and not FULLSTACK_LANE.search(title):
        return "LISTING_PRIMARY_NON_JS_STACK"
    if EXPERIENCE_OVER_FIVE.search(text):
        return "LISTING_EXPERIENCE_OVER_FIVE"
    if re.search(r"\b(?:office[- ]only|only\s+on[- ]site|тільки\s+офіс|лише\s+офіс|тільки\s+в\s+офісі)\b", text, re.IGNORECASE) and not re.search(r"\b(?:remote|віддален|дистанційн)", text, re.IGNORECASE):
        return "LISTING_OFFICE_ONLY"
    return ""


def detail_priority(card: dict) -> tuple:
    """Order detail work by target likelihood without dropping any shortlisted card."""
    title = str(card.get("title", ""))
    listing = str(card.get("listing_text", ""))
    if NODE_NEST_TITLE.search(title):
        base = 0
    elif CORE_WEB_TITLE.search(title):
        base = 1
    elif AI_ROLE_TITLE.search(title):
        base = 2
    elif JS_WEB_LANE.search(listing):
        base = 6
    else:
        base = 7
    # Explicit senior roles often consume a detail navigation only to fail the >5y gate.
    # Keep them, but move them behind non-senior core web/AI roles so challenge-limited
    # runs spend their first detail budget on higher-yield candidates.
    non_js_penalty = 4 if NON_JS_TITLE.search(title) else 0
    senior_penalty = 3 if re.search(r"\b(?:senior|sr\.?|principal|staff)\b", title, re.IGNORECASE) else 0
    tier = base + non_js_penalty + senior_penalty
    return (tier, title.casefold(), str(card.get("url", "")))


def derive_terminal(source: str, state: dict, route_name: str, pages: list[dict]) -> str:
    if source != SOURCE:
        raise SystemExit(f"Unsupported source: {source}")
    final = pages[-1]
    if len(pages) >= 2:
        earlier = {card["url"] for page in pages[:-1] for card in page["cards"]}
        final_urls = {card["url"] for card in final["cards"]}
        if final_urls and not final_urls - earlier and final["next"] is None:
            return "NO_NEW_URLS"
    if final["next"] is None:
        return "NO_NEXT"
    raise SystemExit(f"Jooble route {route_name} still has continuation; exhaustive freshness scan is incomplete")


def coverage_complete(source: str, state: dict) -> bool:
    receipt = state.get("receipt")
    freshness = state.get("freshness")
    if (
        state.get("status") != "SCANNED"
        or not isinstance(receipt, dict)
        or receipt.get("version") != COVERAGE_VERSION
        or receipt.get("sort") != SOURCE_SORTS[source]
        or not isinstance(freshness, dict)
        or receipt.get("freshness") != freshness
        or not state.get("scanned_until")
        or not receipt.get("detail_complete")
        or not receipt.get("classification_complete")
        or receipt.get("blocked_reviews", 0) != 0
    ):
        return False
    try:
        parse_time(state["scanned_until"])
    except (TypeError, ValueError):
        return False
    routes = receipt.get("routes")
    if not isinstance(routes, list) or any(not isinstance(item, dict) for item in routes):
        return False
    if {item.get("name") for item in routes} != set(required_queries(source)):
        return False
    for route in routes:
        if route.get("terminal") not in TERMINALS:
            return False
        if not route.get("filter_proof"):
            return False
        if not isinstance(route.get("pages"), int) or route["pages"] < 1:
            return False
        for field in ("cards", "resolved"):
            if not isinstance(route.get(field), int) or route[field] < 0:
                return False
    return True


def derive_coverage(source: str, state: dict, resolved_urls: set[str]) -> dict:
    observations = state.get("observations") or {}
    routes = observations.get("routes") or {}
    required = required_queries(source)
    observed = observed_candidates(state)
    owner_route: dict[str, str] = {}
    summaries = []
    all_cards = {
        card["url"]
        for route in routes.values()
        for page in route["pages"]
        for card in page["cards"]
    }
    for name in required:
        route = routes[name]
        cards = {}
        for page in route["pages"]:
            for card in page["cards"]:
                cards.setdefault(card["url"], card)
                if card["url"] in observed:
                    owner_route.setdefault(card["url"], name)
        resolved = sum(1 for url in resolved_urls if owner_route.get(url) == name)
        summaries.append(
            {
                "name": name,
                "pages": len(route["pages"]),
                "cards": len(cards),
                "resolved": resolved,
                "filter_proof": route["filter_proof"]["evidence"],
                "terminal": route["terminal"],
            }
        )
    return {
        "version": COVERAGE_VERSION,
        "sort": observations.get("sort", ""),
        "freshness": state["freshness"],
        "unique_cards": len(all_cards),
        "candidates": len(observed),
        "resolved": len(resolved_urls),
        "routes": summaries,
    }


def observe_routes(args: argparse.Namespace) -> None:
    current = active_run()
    if not current:
        raise SystemExit("No IN_PROGRESS run; call start first")
    path, meta = current
    state = require_current_source(meta, args.source, "observe")
    observations, required, completed, next_route = observation_progress(args.source, state)
    if next_route is None:
        raise SystemExit(f"{args.source} is fully observed; call resolve with its exact pending set")
    receipt = receipt_json(args.receipt, "observation")
    expected_receipt = {"version", "sort", "routes"}
    if not isinstance(receipt, dict) or set(receipt) != expected_receipt:
        raise SystemExit(f"Observation fields must be exactly {sorted(expected_receipt)}")
    if receipt["version"] != OBSERVATION_VERSION or receipt["sort"] != SOURCE_SORTS[args.source]:
        raise SystemExit(
            f"Observation requires version {OBSERVATION_VERSION} and strategy {SOURCE_SORTS[args.source]!r}"
        )
    if not isinstance(receipt["routes"], list) or len(receipt["routes"]) != 1:
        raise SystemExit("Observation routes must contain exactly one route")
    raw_route = receipt["routes"][0]
    expected_route = {"name", "filter_proof", "pages"}
    if not isinstance(raw_route, dict) or set(raw_route) != expected_route:
        raise SystemExit(f"Route fields must be exactly {sorted(expected_route)}")
    if raw_route.get("name") != next_route:
        raise SystemExit(f"Observation route must be exactly current next_route {next_route!r}")

    freshness = state.get("freshness")
    if not isinstance(freshness, dict) or set(freshness) != {"key", "param", "days"}:
        raise SystemExit("Jooble freshness state is missing or malformed")
    filter_proof = raw_route["filter_proof"]
    if not isinstance(filter_proof, dict) or set(filter_proof) != {"param", "evidence"}:
        raise SystemExit("filter_proof fields must be exactly ['evidence', 'param']")
    if filter_proof["param"] != freshness["param"]:
        raise SystemExit(
            f"Jooble freshness proof must use date={freshness['param']}, received={filter_proof['param']!r}"
        )
    evidence = re.sub(r"\s+", " ", str(filter_proof["evidence"])).strip()
    if not evidence or len(evidence) > 400 or "date=" not in evidence or "remote-route:" not in evidence or "remote-control:" not in evidence:
        raise SystemExit("Jooble filter proof must prove date freshness and Remote location/filter")
    filter_proof = {"param": freshness["param"], "evidence": evidence}

    if not isinstance(raw_route["pages"], list) or not raw_route["pages"]:
        raise SystemExit(f"Route {next_route} requires a non-empty pages list")
    reference_day = parse_time(meta["started_at"]).astimezone(ZoneInfo(state["date_zone"])).date()
    pages = []
    route_seen_urls: set[str] = set()
    for expected_step, raw_page in enumerate(raw_route["pages"], 1):
        expected_page = {"step", "resolved_url", "next", "visible_cards", "cards"}
        if not isinstance(raw_page, dict) or not expected_page.issubset(raw_page):
            raise SystemExit(f"Page fields must include {sorted(expected_page)}")
        if isinstance(raw_page["step"], bool) or raw_page["step"] != expected_step:
            raise SystemExit(f"Route {next_route} steps must be sequential integers 1..N")
        resolved = route_url(
            args.source, next_route, str(raw_page["resolved_url"]), freshness_param=freshness["param"]
        )
        next_value = raw_page["next"]
        if next_value == "LOAD_MORE":
            pass
        elif next_value is not None:
            next_value = route_url(
                args.source, next_route, str(next_value), freshness_param=freshness["param"]
            )
        if not isinstance(raw_page["cards"], list):
            raise SystemExit(f"Step {expected_step} in {next_route} requires cards list")
        cards = [
            normalize_card(card, args.source, reference_day=reference_day)
            for card in raw_page["cards"]
        ]
        before_ids = [str(item) for item in raw_page.get("before_ids", [])]
        after_ids = [str(item) for item in raw_page.get("after_ids", [])]
        new_ids = [str(item) for item in raw_page.get("newly_discovered_ids", [])]
        observed_ids = [re.search(r"/jdp/(-?\d+)", card["url"]).group(1) for card in cards]
        if before_ids and after_ids and not set(before_ids).issubset(after_ids):
            raise SystemExit(f"Route {next_route} page {expected_step} lost prior IDs")
        if new_ids and set(new_ids) != set(observed_ids):
            raise SystemExit(f"Route {next_route} page {expected_step} newly_discovered_ids mismatch")
        card_urls = [card["url"] for card in cards]
        if len(card_urls) != len(set(card_urls)):
            raise SystemExit(f"Step {expected_step} in {next_route} contains duplicate canonical card URLs")
        if route_seen_urls.intersection(card_urls):
            raise SystemExit(f"Step {expected_step} in {next_route} must contain only newly appeared URLs")
        route_seen_urls.update(card_urls)
        visible_cards = raw_page["visible_cards"]
        if isinstance(visible_cards, bool) or not isinstance(visible_cards, int) or visible_cards < 0:
            raise SystemExit(f"Step {expected_step} in {next_route} visible_cards must be non-negative integer")
        if visible_cards != len(cards):
            raise SystemExit(
                f"Step {expected_step} in {next_route} visible_cards={visible_cards} but cards={len(cards)}"
            )
        pages.append(
            {
                "step": expected_step,
                "resolved_url": resolved,
                "next": next_value,
                "visible_cards": len(cards),
                "cards": cards,
            }
        )
    for index, page in enumerate(pages[:-1]):
        if page["next"] is None:
            raise SystemExit(f"Route {next_route} step {index + 1} has no continuation before final step")
        if page["next"] != "LOAD_MORE" and page["next"] != pages[index + 1]["resolved_url"]:
            raise SystemExit(f"Route {next_route} step {index + 1} next URL does not match next resolved_url")
    terminal = derive_terminal(args.source, state, next_route, pages)
    if any(card["title"].casefold() in PLACEHOLDERS for page in pages for card in page["cards"]):
        raise SystemExit(f"Jooble route {next_route} contains placeholder titles")

    routes = dict(observations["routes"])
    routes[next_route] = {
        "name": next_route,
        "filter_proof": filter_proof,
        "terminal": terminal,
        "pages": pages,
    }
    state["observations"] = {"version": OBSERVATION_VERSION, "sort": receipt["sort"], "routes": routes}
    append_diagnostic(
        path,
        "route-observation",
        {
            "route": next_route,
            "freshness": freshness,
            "filter_proof": filter_proof,
            "terminal": terminal,
            "pages": [
                {
                    "step": page["step"],
                    "resolved_url": page["resolved_url"],
                    "next": page["next"],
                    "cards": page["cards"],
                }
                for page in pages
            ],
        },
    )
    write_markdown(path, meta)

    completed = [*completed, next_route]
    next_route = required[len(completed)] if len(completed) < len(required) else None
    if next_route is not None:
        print(
            json.dumps(
                {
                    "source": args.source,
                    "observed_route": completed[-1],
                    "completed_routes": len(completed),
                    "total_routes": len(required),
                    "next_source": args.source,
                    "source_file": SOURCE_FILES[args.source],
                    "next_step": "observe",
                    "sort": SOURCE_SORTS[args.source],
                    "next_route": next_route,
                    "freshness": freshness,
                },
                ensure_ascii=False,
            )
        )
        return

    candidates = observed_candidates(state)
    known = known_urls_for(path, current_source=args.source)
    listing_rejects = {
        url: safe_listing_reject(card)
        for url, card in candidates.items()
        if safe_listing_reject(card)
    }
    shortlist = {url: card for url, card in candidates.items() if url not in listing_rejects}
    pending_urls = sorted(set(shortlist) - known, key=lambda url: detail_priority(shortlist[url]))
    pending = [
        {
            "url": url,
            "title": candidates[url]["title"],
            "company": candidates[url]["company"],
            "date": shortlist[url]["date"] or "UNKNOWN",
            "carrier_url": shortlist[url].get("carrier_url", ""),
            "listing_text": shortlist[url].get("listing_text", ""),
            "location_text": shortlist[url].get("location_text", ""),
            "origin_url": shortlist[url].get("origin_url", ""),
        }
        for url in pending_urls
    ]
    unique_cards = len({
        card["url"] for route in routes.values() for page in route["pages"] for card in page["cards"]
    })
    print(
        json.dumps(
            {
                "source": args.source,
                "observed_route": completed[-1],
                "completed_routes": len(completed),
                "total_routes": len(required),
                "unique_cards": unique_cards,
                "candidates": len(candidates),
                "pending_count": len(pending),
                "safe_listing_rejects": len(listing_rejects),
                "detail_shortlist": len(pending),
                "pending": pending,
                "terminals": {name: routes[name]["terminal"] for name in required},
                "next_source": args.source,
                "source_file": SOURCE_FILES[args.source],
                "next_step": "resolve",
                "sort": SOURCE_SORTS[args.source],
                "next_route": None,
                "freshness": freshness,
            },
            ensure_ascii=False,
        )
    )


def workflow_next(path: Path, meta: dict) -> dict:
    source = next_source(meta)
    if source is None:
        return {"next_source": None, "next_step": "finish"}
    state = meta["sources"][source]
    _, _, _, next_route = observation_progress(source, state)
    if next_route is not None:
        return {
            "next_source": source,
            "source_file": SOURCE_FILES[source],
            "next_step": "observe",
            "sort": SOURCE_SORTS[source],
            "next_route": next_route,
            "freshness": state.get("freshness"),
        }
    candidates = observed_candidates(state)
    known = known_urls_for(path, current_source=source)
    listing_rejects = {url: safe_listing_reject(card) for url, card in candidates.items() if safe_listing_reject(card)}
    shortlist = {url: card for url, card in candidates.items() if url not in listing_rejects}
    pending_urls = sorted(set(shortlist) - known, key=lambda url: detail_priority(shortlist[url]))
    return {
        "next_source": source,
        "source_file": SOURCE_FILES[source],
        "next_step": "resolve",
        "next_route": None,
        "pending_count": len(pending_urls),
        "safe_listing_rejects": len(listing_rejects),
        "detail_shortlist": len(pending_urls),
        "freshness": state.get("freshness"),
        "pending": [
            {
                "url": url,
                "title": shortlist[url]["title"],
                "company": shortlist[url]["company"],
                "date": shortlist[url]["date"] or "UNKNOWN",
                "carrier_url": shortlist[url].get("carrier_url", ""),
                "listing_text": shortlist[url].get("listing_text", ""),
                "location_text": shortlist[url].get("location_text", ""),
                "origin_url": shortlist[url].get("origin_url", ""),
            }
            for url in pending_urls
        ],
    }


def write_markdown(path: Path, meta: dict) -> None:
    items = read_items(jsonl_for(path))
    groups = (
        ("Бронювання підтверджено", [item for item in items if item["reservation"] == "CONFIRMED"]),
        ("Підходять", [item for item in items if item["reservation"] != "CONFIRMED" and item["decision"] == "MATCH"]),
        ("Потрібно перевірити", [item for item in items if item["reservation"] != "CONFIRMED" and item["decision"] == "REVIEW"]),
        ("Отклонены", [item for item in items if item["reservation"] != "CONFIRMED" and item["decision"] == "REJECT"]),
    )
    lines = [
        f"<!-- RADAR_JOOBLE {json.dumps(meta, ensure_ascii=False, separators=(',', ':'))} -->",
        "",
        f"# {path.stem}",
        "",
        f"Статус: **{meta['status']}**",
        "",
        "| Джерело | Статус | Період від | Покриття | Причина |",
        "|---|---|---|---|---|",
    ]
    for source in SOURCES:
        state = meta["sources"][source]
        receipt = state.get("receipt") or {}
        routes = receipt.get("routes") or []
        coverage = "—"
        if routes:
            route_cards = sum(item["cards"] for item in routes)
            card_text = (
                f"{receipt['unique_cards']} унік. карток"
                if isinstance(receipt.get("unique_cards"), int)
                else f"{route_cards} карток у маршрутах"
            )
            freshness_key = (receipt.get("freshness") or state.get("freshness") or {}).get("key", "?")
            coverage = (
                f"freshness {freshness_key} · {len(routes)} маршрутів · "
                f"{sum(item['pages'] for item in routes)} стор. · {card_text} · "
                f"{sum(item['resolved'] for item in routes)} resolved"
            )
        elif state.get("observations", {}).get("routes"):
            observed_routes = state["observations"]["routes"].values()
            page_count = sum(len(item["pages"]) for item in observed_routes)
            card_count = len({card["url"] for item in observed_routes for page in item["pages"] for card in page["cards"]})
            coverage = f"{len(state['observations']['routes'])} маршрутів · {page_count} стор. · {card_count} карток · триває"
        lines.append(f"| {source} | {state['status']} | {state['from'][:16]} | {coverage} | {state.get('reason') or '—'} |")
    lines.append("")
    for heading, values in groups:
        lines += [f"## {heading}", ""]
        values.sort(key=lambda item: (item.get("published_date") or "", item.get("title") or ""), reverse=True)
        if not values:
            lines += ["—", ""]
            continue
        for item in values:
            place = " / ".join(value for value in (item["work_mode"], item.get("city")) if value) or "UNKNOWN"
            lines.append(
                f"- [{item['title']}]({item['url']}) — {item['company']} · {item['source']} · "
                f"{item.get('published_date') or 'дата невідома'} · {place} · бронювання: {item['reservation']}"
            )
            if item.get("caution"):
                lines.append(f"  - Увага: {item['caution']}")
        lines.append("")
    temp_path = path.with_suffix(".md.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines).rstrip() + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def latest_coverage_watermark(previous: list[tuple[Path, dict]], source: str) -> datetime | None:
    for _, old in reversed(previous):
        state = old.get("sources", {}).get(source, {})
        scanned_until = state.get("scanned_until")
        if coverage_complete(source, state) and scanned_until:
            return parse_time(scanned_until)
    return None


def select_freshness(previous: list[tuple[Path, dict]], source: str, started: datetime, mode: str, override: str | None = None) -> tuple[dict, datetime]:
    if mode == "TEST":
        key = override or "24h"
        if key not in FRESHNESS:
            raise SystemExit(f"Unsupported TEST freshness override: {key}")
        spec = {"key": key, **FRESHNESS[key]}
        return spec, started - timedelta(days=spec["days"])
    watermark = latest_coverage_watermark(previous, source)
    if watermark is None:
        spec = {"key": "3d", **FRESHNESS["3d"]}
        return spec, started - timedelta(days=3)
    gap = started - watermark
    if gap < timedelta(0):
        gap = timedelta(0)
    if gap <= timedelta(days=2):
        spec = {"key": "3d", **FRESHNESS["3d"]}
    elif gap <= timedelta(days=6):
        spec = {"key": "7d", **FRESHNESS["7d"]}
    else:
        raise SystemExit(
            "Last proven Jooble coverage is older than 6 days. The website freshness filters can no longer prove a gap-free incremental scan; "
            "do not emit a misleading COMPLETE result. Run a new bootstrap intentionally after reviewing the gap."
        )
    return spec, watermark


def blocked_complete(state: dict, next_route: str) -> bool:
    receipt = state.get("receipt")
    attempts = receipt.get("attempts") if isinstance(receipt, dict) else None
    if state.get("status") != "BLOCKED" or not state.get("reason") or not isinstance(attempts, list):
        return False
    return len(attempts) >= 2 and all(
        isinstance(item, dict)
        and item.get("route") == next_route
        and isinstance(item.get("error"), str)
        and bool(item["error"].strip())
        for item in attempts
    )


def requested_mode(args: argparse.Namespace) -> str:
    return "TEST" if args.test_live else "INCREMENTAL"


def start_or_resume(args: argparse.Namespace) -> None:
    started = now()
    mode = requested_mode(args)
    if mode != "TEST" and args.freshness is not None:
        raise SystemExit("--freshness is supported only with --test-live")
    current = active_run()
    if current:
        path, meta = current
        if meta.get("schema_version") != OBSERVATION_VERSION:
            raise SystemExit(
                f"Legacy active run cannot resume under {COVERAGE_VERSION}; move that active pair out of results first"
            )
        if meta.get("mode") != mode:
            raise SystemExit(f"A {meta.get('mode')} run is already active; resume it with the same start mode")
        state = meta["sources"][SOURCE]
        response = {
            "resumed": True,
            "mode": mode,
            "source_status": state["status"],
            "markdown": str(path),
            "jsonl": str(jsonl_for(path)),
            "diagnostics": str(diagnostics_for(path)),
            "from": {SOURCE: state["from"]},
            "until": meta["until"],
            "date_reference": source_reference_days(meta),
            "freshness": state["freshness"],
        }
        response.update(workflow_next(path, meta))
        print(json.dumps(response, ensure_ascii=False))
        return

    RESULTS.mkdir(parents=True, exist_ok=True)
    TEST_RESULTS.mkdir(parents=True, exist_ok=True)
    previous = runs(RESULTS)
    freshness, source_from = select_freshness(previous, SOURCE, started, mode, args.freshness)
    frozen_until = started
    source_states = {
        SOURCE: {
            "status": "PENDING",
            "from": iso(source_from),
            "until": iso(frozen_until),
            "date_zone": SOURCE_DATE_ZONES[SOURCE],
            "freshness": freshness,
            "reason": "",
            "receipt": None,
            "scanned_at": None,
            "scanned_until": None,
            "observations": empty_observations(),
        }
    }
    meta = {
        "schema_version": OBSERVATION_VERSION,
        "coverage_version": COVERAGE_VERSION,
        "ruleset_version": RULESET_VERSION,
        "status": "IN_PROGRESS",
        "mode": mode,
        "from": iso(source_from),
        "until": iso(frozen_until),
        "started_at": iso(started),
        "sources": source_states,
    }
    output_directory = TEST_RESULTS if mode == "TEST" else RESULTS
    if mode == "TEST":
        path = unused_test_path(
            output_directory,
            test_result_name(source_from, frozen_until, started),
        )
    else:
        path = unused_result_path(output_directory, result_name(source_from, frozen_until))
    jsonl_for(path).touch(exist_ok=False)
    diagnostics_for(path).touch(exist_ok=False)
    write_markdown(path, meta)
    append_diagnostic(
        path,
        "run-created",
        {
            "mode": mode,
            "from": iso(source_from),
            "until": iso(frozen_until),
            "freshness": freshness,
            "routes": required_queries(SOURCE),
            "ruleset": RULESET_VERSION,
        },
    )
    response = {
        "resumed": False,
        "mode": mode,
        "source_status": source_states[SOURCE]["status"],
        "markdown": str(path),
        "jsonl": str(jsonl_for(path)),
        "diagnostics": str(diagnostics_for(path)),
        "from": {SOURCE: iso(source_from)},
        "until": iso(frozen_until),
        "date_reference": source_reference_days(meta),
        "freshness": freshness,
    }
    response.update(workflow_next(path, meta))
    print(json.dumps(response, ensure_ascii=False))


def resolve_details(args: argparse.Namespace) -> None:
    current = active_run()
    if not current:
        raise SystemExit("No IN_PROGRESS run; call start first")
    path, meta = current
    state = require_current_source(meta, args.source, "resolve")
    _, _, _, next_route = observation_progress(args.source, state)
    if next_route is not None:
        raise SystemExit(f"Observe all {args.source} routes before resolve; next_route={next_route!r}")
    receipt = receipt_json(args.receipt, "detail receipt")
    if not isinstance(receipt, dict) or not {"version", "details"}.issubset(receipt):
        raise SystemExit("Detail receipt must contain ['details', 'version']")
    if receipt["version"] != OBSERVATION_VERSION or not isinstance(receipt["details"], list):
        raise SystemExit(f"Detail receipt requires version {OBSERVATION_VERSION} and a details list")

    candidates = observed_candidates(state)
    known = known_urls_for(path, current_source=args.source)
    listing_rejects = {url: safe_listing_reject(card) for url, card in candidates.items() if safe_listing_reject(card)}
    pending = set(candidates) - known - set(listing_rejects)
    blocked = receipt.get("blocked", [])
    if not isinstance(blocked, list) or any(not isinstance(item, dict) for item in blocked):
        raise SystemExit("blocked must be a list of listing-only detail reviews")
    reference_day = parse_time(state["until"]).astimezone(ZoneInfo(state["date_zone"])).date()
    normalized = []
    seen: set[str] = set()
    for raw in receipt["details"]:
        if not isinstance(raw, dict) or set(raw) != DETAIL_FIELDS:
            raise SystemExit(f"Detail fields must be exactly {sorted(DETAIL_FIELDS)}")
        if any(not isinstance(raw[field], str) for field in DETAIL_FIELDS):
            raise SystemExit("Every detail fact must be a string")
        url = source_url(args.source, raw["url"], vacancy=True)
        final_url = source_url(args.source, raw["final_url"], vacancy=True)
        if url != final_url:
            raise SystemExit(f"Detail final_url does not canonical-match url: {url}")
        if url in seen:
            raise SystemExit(f"Duplicate detail URL: {url}")
        seen.add(url)
        title = re.sub(r"\s+", " ", raw["title"].strip())
        company = re.sub(r"\s+", " ", raw["company"].strip())
        if not title or not company or title.casefold() in PLACEHOLDERS or company.casefold() in PLACEHOLDERS:
            raise SystemExit(f"Detail title/company must be real values: {url}")
        if len(title) + len(company) > 240:
            raise SystemExit(f"Detail title/company are implausibly long: {url}")
        published = normalize_publication(raw["published_date"], reference_day=reference_day)
        location_text = bounded_text(raw["location_text"], label="Detail location_text", limit=LOCATION_TEXT_LIMIT)
        detail_text = bounded_text(raw["detail_text"], label="Detail detail_text", limit=DETAIL_TEXT_LIMIT)
        facts = derive_detail_facts(args.source, title, location_text, detail_text)
        city = facts["city"]
        if facts["work_mode"] in {"HYBRID", "OFFICE"} and not city:
            city = "не вказано"
        rule = facts["reject_rule"]
        review_reason = facts["review_reason"]
        target_text = f"{title}\n{detail_text}"
        target_evidence = bool(
            POSITIVE_WEB.search(target_text)
            or (AI_TOOLING.search(target_text) and JS_WEB.search(target_text))
        )
        if not rule and not target_evidence:
            rule = "NOT_TARGET_WEB_JS"
        primary_title_target = bool(JS_WEB_LANE.search(title) or AI_ROLE_TITLE.search(title))
        if not rule and target_evidence and not primary_title_target and not review_reason:
            # A secondary JS/web mention in the description is not enough for an automatic MATCH.
            # Keep ambiguous generic titles visible as REVIEW instead of silently accepting them.
            review_reason = "Primary target role is not confirmed by title"
        junior_frontend = bool(
            JUNIOR.search(title) and FRONTEND_LANE.search(title) and not FULLSTACK_LANE.search(title)
        )
        mixed_allowed_frontend_level = bool(
            re.search(r"\bjunior\s*(?:/|[-–])\s*(?:middle|senior)\b", title, re.IGNORECASE)
        )
        if junior_frontend and not mixed_allowed_frontend_level and not rule:
            rule = "FRONTEND_LEVEL_TOO_LOW"
        normalized.append((url, title, company, published, city, facts, rule, review_reason))

    if not seen.issubset(pending):
        raise SystemExit(
            f"Detail URL set must be a subset of pending; missing={sorted(pending - seen)}, extra={sorted(seen - pending)}"
        )

    outcomes: list[dict] = []
    new_items = []
    for url, title, company, detail_date, city, facts, rule, review_reason in normalized:
        published = detail_date if detail_date is not None else candidates[url]["date"]
        if rule:
            new_items.append(
                {
                    "url": url,
                    "source": args.source,
                    "title": title,
                    "company": company,
                    "published_date": published,
                    "decision": "REJECT",
                    "work_mode": facts["work_mode"],
                    "city": city,
                    "reservation": facts["reservation"],
                    "caution": rule,
                }
            )
            outcomes.append({
                "url": url, "title": title, "company": company, "result": "REJECT", "rule": rule,
                "published_date": published, "work_mode": facts["work_mode"],
            })
            continue
        senior_fullstack = bool(SENIOR.search(title) and FULLSTACK_LANE.search(title))
        # Jooble freshness is already proven at discovery by the active date=<param> route.
        # A missing detail-level publication date is useful metadata, not a reason to downgrade MATCH.
        decision = "REVIEW" if (senior_fullstack and not facts["frontend_heavy"]) or review_reason else "MATCH"
        caution = review_reason or ("Дата публікації не вказана; freshness підтверджено Jooble route" if published is None else "")
        new_items.append(
            {
                "url": url,
                "source": args.source,
                "title": title,
                "company": company,
                "published_date": published,
                "decision": decision,
                "work_mode": facts["work_mode"],
                "city": city,
                "reservation": facts["reservation"],
                "caution": caution,
            }
        )
        outcomes.append({
            "url": url, "title": title, "company": company, "result": decision, "rule": "",
            "published_date": published, "work_mode": facts["work_mode"],
        })

    for url, rule in listing_rejects.items():
        reject_item = {"url": url, "source": args.source, "title": candidates[url]["title"], "company": candidates[url]["company"], "published_date": candidates[url]["date"], "decision": "REJECT", "work_mode": "UNKNOWN", "city": "", "reservation": "NOT_MENTIONED", "caution": rule}
        new_items.append(reject_item)
        outcomes.append({"url": url, "title": candidates[url]["title"], "company": candidates[url]["company"], "result": "REJECT", "rule": rule, "published_date": candidates[url]["date"], "work_mode": "UNKNOWN"})
    for item in blocked:
        url = source_url(args.source, item.get("url", ""), vacancy=True)
        if url not in pending or url in seen:
            raise SystemExit(f"Blocked detail is not unresolved shortlist candidate: {url}")
        title = re.sub(r"\s+", " ", str(item.get("title") or candidates[url]["title"]).strip())
        company = re.sub(r"\s+", " ", str(item.get("company") or candidates[url]["company"]).strip())
        new_items.append({"url": url, "source": args.source, "title": title, "company": company, "published_date": candidates[url]["date"], "decision": "REVIEW", "work_mode": "UNKNOWN", "city": "", "reservation": "NOT_MENTIONED", "caution": "DETAIL_BLOCKED / listing evidence only"})
    target = jsonl_for(path)
    existing = [
        item for item in read_items(target)
        if not (item.get("source") == args.source and canonical_url(item.get("url", "")) in seen)
    ]
    temp_path = target.with_suffix(".jsonl.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for item in [*existing, *new_items]:
            handle.write(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, target)

    append_diagnostic(
        path,
        "classification",
        {
            "ruleset": RULESET_VERSION,
        "resolved": len(seen),
        "listing_rejects": len(listing_rejects),
        "blocked_reviews": len(blocked),
            "items": outcomes,
            "counts": {
                key: sum(item["result"] == key for item in outcomes)
                for key in ("MATCH", "REVIEW", "REJECT")
            },
        },
    )
    if path.parent != TEST_RESULTS:
        persist_seen(outcomes, path.stem)

    state["status"] = "SCANNED"
    state["receipt"] = derive_coverage(args.source, state, seen)
    state["receipt"]["safe_listing_rejects"] = len(listing_rejects)
    state["receipt"]["detail_shortlist"] = len(pending)
    state["receipt"]["blocked_reviews"] = len(blocked)
    state["receipt"]["detail_complete"] = not blocked and seen == pending
    state["receipt"]["classification_complete"] = not blocked and seen == pending
    state.pop("observations", None)
    state["scanned_at"] = iso(now())
    state["scanned_until"] = meta["until"]
    write_markdown(path, meta)
    outcome_counts = {
        result: sum(item["result"] == result for item in outcomes)
        for result in ("MATCH", "REVIEW", "REJECT")
    }
    response = {
        "source": args.source,
        "status": "SCANNED",
        "resolved": len(seen),
        "counts": outcome_counts,
    }
    response.update(workflow_next(path, meta))
    print(json.dumps(response, ensure_ascii=False))


def block_source(args: argparse.Namespace) -> None:
    current = active_run()
    if not current:
        raise SystemExit("No IN_PROGRESS run; call start first")
    path, meta = current
    state = require_current_source(meta, args.source, "block")
    _, _, _, next_route = observation_progress(args.source, state)
    target = next_route
    if target is None:
        candidates = observed_candidates(state)
        pending = set(candidates) - known_urls_for(path, current_source=args.source)
        if not pending:
            raise SystemExit(f"{args.source} has no unresolved details; call resolve with empty details")
        target = "DETAILS"
    receipt = receipt_json(args.receipt, "block receipt")
    candidate_state = {"status": "BLOCKED", "reason": args.reason.strip(), "receipt": receipt}
    if not blocked_complete(candidate_state, target):
        raise SystemExit(
            f"BLOCKED requires a reason and at least two technical attempts with route={target!r} "
            "and a non-empty error"
        )
    state.update(status="BLOCKED", reason=args.reason.strip(), receipt=receipt, scanned_at=None, scanned_until=None)
    write_markdown(path, meta)
    response = {"source": args.source, "status": "BLOCKED", "blocked_target": target}
    response.update(workflow_next(path, meta))
    print(json.dumps(response, ensure_ascii=False))


def finish_run(_: argparse.Namespace) -> None:
    current = active_run()
    if not current:
        raise SystemExit("No IN_PROGRESS run; call start first")
    old_md, meta = current
    old_jsonl = jsonl_for(old_md)
    items = read_items(old_jsonl)
    urls = [canonical_url(item["url"]) for item in items]
    if len(urls) != len(set(urls)):
        raise SystemExit("Duplicate URLs in current JSONL")
    if any(source not in meta["sources"] for source in SOURCES):
        raise SystemExit("Missing source state")
    pending = [source for source in SOURCES if meta["sources"][source].get("status") == "PENDING"]
    if pending:
        raise SystemExit(f"Cannot finish while sources are PENDING: {', '.join(pending)}. Leave the run active and continue it.")
    meta["finished_at"] = iso(now())
    meta["status"] = "COMPLETE" if all(coverage_complete(source, meta["sources"][source]) for source in SOURCES) else "PARTIAL"
    if meta.get("mode") == "TEST":
        new_md, new_jsonl = old_md, old_jsonl
    else:
        new_base = result_name(
            min(parse_time(meta["sources"][source]["from"]) for source in SOURCES),
            display_until(meta),
        )
        new_md, new_jsonl = old_md.parent / f"{new_base}.md", old_md.parent / f"{new_base}.jsonl"
    old_diagnostics = diagnostics_for(old_md)
    new_diagnostics = diagnostics_for(new_md)
    if new_md != old_md:
        os.replace(old_jsonl, new_jsonl)
        if old_diagnostics.exists():
            os.replace(old_diagnostics, new_diagnostics)
        os.replace(old_md, new_md)
    write_markdown(new_md, meta)
    rendered = new_md.read_text(encoding="utf-8")
    if sum(rendered.count(f"]({url})") for url in urls) != len(urls):
        raise SystemExit("Markdown and JSONL URL contents differ")
    pairs = []
    for path in new_md.parent.glob("*.md"):
        run_meta = read_meta(path)
        if (
            path.with_suffix(".jsonl").exists()
            and run_meta
            and run_meta.get("status") in {"COMPLETE", "PARTIAL"}
        ):
            pairs.append((path, path.with_suffix(".jsonl"), run_meta))
    pairs.sort(key=lambda item: (item[2] or {}).get("started_at", ""))
    pruned = []
    while len(pairs) > MAX_RUNS:
        md_path, json_path, _ = pairs.pop(0)
        md_path.unlink()
        json_path.unlink()
        for extra in (
            diagnostics_for(md_path),
            md_path.with_name(f"{md_path.stem}.manifest.json"),
            md_path.with_name(f"{md_path.stem}.calibration.zip"),
        ):
            if extra.exists():
                extra.unlink()
        pruned.append(md_path.stem)
    counts = {
        "MATCH": sum(item["decision"] == "MATCH" for item in items),
        "REVIEW": sum(item["decision"] == "REVIEW" for item in items),
        "CONFIRMED": sum(item["reservation"] == "CONFIRMED" for item in items),
    }
    per_source = {}
    for source in SOURCES:
        state = meta["sources"][source]
        receipt = state.get("receipt") or {}
        per_source[source] = {
            "status": state["status"],
            "cards": receipt.get("unique_cards", 0),
            "candidates": receipt.get("candidates", 0),
            "resolved": receipt.get("resolved", 0),
        }
    elapsed_seconds = int((parse_time(meta["finished_at"]) - parse_time(meta["started_at"])).total_seconds())
    calibration_bundle = None
    if meta.get("mode") == "TEST":
        calibration_bundle = new_md.with_name(f"{new_md.stem}.calibration.zip")
        manifest = {
            "radar": "RADAR-JOOBLE",
            "schema_version": OBSERVATION_VERSION,
            "coverage_version": COVERAGE_VERSION,
            "ruleset_version": RULESET_VERSION,
            "status": meta["status"],
            "mode": meta.get("mode"),
            "from": meta.get("from"),
            "until": meta.get("until"),
            "freshness": meta["sources"][SOURCE].get("freshness"),
            "routes": required_queries(SOURCE),
            "counts": counts,
            "sources": per_source,
            "files_sha256": {
                name: sha256_file(ROOT / name)
                for name in (
                    "radar.py",
                    "browser-runner.mjs",
                    "start.md",
                    "AGENTS.md",
                    "DEVELOPMENT.md",
                    "CALIBRATE-PROMPT.md",
                    "sources/jooble.md",
                )
                if (ROOT / name).exists()
            },
        }
        manifest_path = new_md.with_name(f"{new_md.stem}.manifest.json")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        with zipfile.ZipFile(calibration_bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for artifact in (new_md, new_jsonl, new_diagnostics, manifest_path):
                if artifact.exists():
                    archive.write(artifact, arcname=artifact.name)
            for relative in (
                "radar.py",
                "browser-runner.mjs",
                "start.md",
                "AGENTS.md",
                "DEVELOPMENT.md",
                "CALIBRATE-PROMPT.md",
                "sources/jooble.md",
            ):
                artifact = ROOT / relative
                if artifact.exists():
                    archive.write(artifact, arcname=f"runtime/{relative}")
    payload = {
        "status": meta["status"], "markdown": str(new_md), "jsonl": str(new_jsonl),
        "diagnostics": str(new_diagnostics),
        "elapsed_seconds": elapsed_seconds, "sources": per_source,
        "counts": counts, "pruned": pruned, "next_source": None, "next_step": None,
    }
    if calibration_bundle is not None:
        payload["calibration_bundle"] = str(calibration_bundle)
    print(json.dumps(payload, ensure_ascii=False))


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    commands = cli.add_subparsers(dest="command", required=True)
    start = commands.add_parser("start")
    start.add_argument(
        "--test-live",
        action="store_true",
        help="Isolated calibration scan using Jooble freshness filter",
    )
    start.add_argument(
        "--freshness",
        choices=sorted(FRESHNESS),
        default=None,
        help="TEST-only freshness window override; normal mode keeps automatic overlap selection",
    )
    start.set_defaults(func=start_or_resume)
    observe = commands.add_parser("observe")
    observe.add_argument("--source", required=True, choices=SOURCES)
    observe.add_argument("--receipt", required=True, help="JSON receipt, or - to read it from stdin")
    observe.set_defaults(func=observe_routes)
    resolve = commands.add_parser("resolve")
    resolve.add_argument("--source", required=True, choices=SOURCES)
    resolve.add_argument("--receipt", required=True, help="JSON receipt, or - to read it from stdin")
    resolve.set_defaults(func=resolve_details)
    block = commands.add_parser("block")
    block.add_argument("--source", required=True, choices=SOURCES)
    block.add_argument("--reason", required=True)
    block.add_argument(
        "--receipt", required=True,
        help="JSON or - from stdin: at least two attempts for the current next route or DETAILS",
    )
    block.set_defaults(func=block_source)
    commands.add_parser("finish").set_defaults(func=finish_run)
    return cli


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
