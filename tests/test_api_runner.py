import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("api_runner", ROOT / "api-runner.py")
api = importlib.util.module_from_spec(SPEC)
sys.modules["api_runner"] = api
SPEC.loader.exec_module(api)


def fixture_jobs():
    data = json.loads((ROOT / "tests" / "fixtures" / "jooble-api-response.json").read_text(encoding="utf-8"))
    return [api.normalize_api_job(raw, "fixture") for raw in data["jobs"]]


def test_config_is_four_bounded_queries_with_hybrid_lane():
    config = api.load_config(ROOT / "sources" / "jooble-api.json")
    assert len(config["queries"]) == 4
    assert config["result_on_page"] == 100
    assert config["location"] == "Ukraine"
    assert all(q.location == "Ukraine" for q in config["queries"])
    assert any("hybrid" in q.keywords.casefold() for q in config["queries"])


def test_request_payload_has_documented_fields_and_no_secret():
    config = api.load_config(ROOT / "sources" / "jooble-api.json")
    payload = api.request_payload(config, config["queries"][0])
    assert set(payload) == {"keywords", "location", "page", "ResultOnPage", "SearchMode", "companysearch"}
    text = json.dumps(payload, ensure_ascii=False)
    assert "JOOBLE_API_KEY" not in text


def test_timestamp_accepts_seven_fractional_digits():
    value = api.parse_iso_timestamp("2026-09-21T08:00:00.1234567Z")
    assert value is not None and value.microsecond == 123456


def test_signed_jdp_identity_is_canonical():
    job = fixture_jobs()[1]
    assert job["identity"] == "jdp:-222222"
    assert job["jdp_id"] == "-222222"


def test_hybrid_is_eligible_not_rejected():
    item = api.classify_api_job(fixture_jobs()[2])
    assert item["work_mode"] == "HYBRID"
    assert item["decision"] == "MATCH"
    assert item["rule"] == ""


def test_unknown_mode_is_review_not_dropped():
    item = api.classify_api_job(fixture_jobs()[1])
    assert item["work_mode"] == "UNKNOWN"
    assert item["decision"] == "REVIEW"
    assert "not explicitly confirmed" in item["caution"]


def test_office_only_is_rejected():
    item = api.classify_api_job(fixture_jobs()[4])
    assert item["work_mode"] == "OFFICE"
    assert item["decision"] == "REJECT"


def test_primary_non_js_role_is_rejected_even_if_react_mentioned():
    item = api.classify_api_job(fixture_jobs()[3])
    assert item["decision"] == "REJECT"
    assert item["rule"].endswith("PRIMARY_NON_JS_STACK")


def test_unknown_updated_stays_review_with_freshness_caution():
    item = api.classify_api_job(fixture_jobs()[5], freshness_unknown=True)
    assert item["decision"] == "REVIEW"
    assert "freshness is not proven" in item["caution"]


def test_env_permissions_fail_closed_without_echoing_key(tmp_path):
    path = tmp_path / ".env.local"
    path.write_text("JOOBLE_API_KEY=super-secret-value\n", encoding="utf-8")
    path.chmod(0o644)
    with pytest.raises(api.ApiRunnerError) as exc:
        api.load_api_key(path)
    assert "super-secret-value" not in str(exc.value)


def test_env_is_parsed_as_data_not_shell(tmp_path):
    path = tmp_path / ".env.local"
    path.write_text("# comment\nJOOBLE_API_KEY='abc-123'\nOTHER=$(echo bad)\n", encoding="utf-8")
    path.chmod(0o600)
    assert api.load_api_key(path) == "abc-123"


def test_external_link_is_rejected():
    raw = {
        "id": 9,
        "title": "React Developer",
        "location": "Remote",
        "snippet": "React TypeScript",
        "link": "https://evil.example/jdp/9",
        "company": "X",
        "updated": "2099-09-21T08:00:00Z",
    }
    assert api.normalize_api_job(raw, "q") is None


def test_secret_guard_deletes_all_output_files(tmp_path):
    secret = "super-secret-key"
    paths = [tmp_path / "a.md", tmp_path / "b.jsonl", tmp_path / "c.json"]
    paths[0].write_text("safe", encoding="utf-8")
    paths[1].write_text("safe", encoding="utf-8")
    paths[2].write_text(f"oops {secret}", encoding="utf-8")
    with pytest.raises(api.ApiRunnerError) as exc:
        api.ensure_no_secret_leak(paths, secret)
    assert str(exc.value) == "SECRET_LEAK_PREVENTED"
    assert not any(p.exists() for p in paths)


def test_seen_same_version_is_suppressed_but_update_resurfaces():
    item = {"identity": "jdp:42", "updated_at": "2026-09-21T08:00:00Z", "decision": "MATCH"}
    previous = {"identity": "jdp:42", "ruleset": api.API_RULESET_VERSION, "updated_at": item["updated_at"], "decision": "MATCH"}
    assert api.seen_item_unchanged(item, previous)
    previous["updated_at"] = "2026-09-20T08:00:00Z"
    assert not api.seen_item_unchanged(item, previous)


def test_end_to_end_fixture_writes_only_match_review_to_jsonl(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(api, "TEST_RESULTS_DIR", tmp_path / "test")
    monkeypatch.setattr(api, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(api, "RUN_DIAGNOSTICS_DIR", tmp_path / "state" / "api-runs")
    monkeypatch.setattr(api, "SEEN_PATH", tmp_path / "state" / "api-seen.jsonl")
    monkeypatch.setattr(api, "USAGE_PATH", tmp_path / "state" / "api-usage.json")
    monkeypatch.setattr(api, "WATERMARK_PATH", tmp_path / "state" / "api-watermark.json")
    monkeypatch.setattr(api, "LOCK_PATH", tmp_path / "state" / "api-run.lock")
    monkeypatch.setattr(api, "utc_now", lambda: datetime(2099, 9, 21, 10, 0, tzinfo=timezone.utc))
    args = api.build_parser().parse_args(["run", "--fixture", str(ROOT / "tests" / "fixtures" / "jooble-api-response.json")])
    result = api.execute(args)
    assert result["status"] == "DONE"
    assert Path(result["markdown"]).exists() and Path(result["jsonl"]).exists()
    rows = [json.loads(line) for line in Path(result["jsonl"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert all(row["decision"] in {"MATCH", "REVIEW"} for row in rows)
    assert not any(row["decision"] == "REJECT" for row in rows)
    assert any(row["work_mode"] == "HYBRID" for row in rows)
    assert any(row["decision"] == "REVIEW" and row["work_mode"] == "UNKNOWN" for row in rows)
    assert result["counts"]["REJECT"] >= 2


def test_blocked_transport_still_writes_two_user_files(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(api, "RUN_DIAGNOSTICS_DIR", tmp_path / "state" / "api-runs")
    monkeypatch.setattr(api, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(api, "USAGE_PATH", tmp_path / "state" / "api-usage.json")
    monkeypatch.setattr(api, "WATERMARK_PATH", tmp_path / "state" / "api-watermark.json")
    monkeypatch.setattr(api, "LOCK_PATH", tmp_path / "state" / "api-run.lock")
    monkeypatch.setattr(api, "load_api_key", lambda: "hidden")
    monkeypatch.setattr(api, "perform_request", lambda *a, **k: (_ for _ in ()).throw(api.ApiRunnerError("network blocked")))
    args = api.build_parser().parse_args(["run", "--force"])
    result = api.execute(args)
    assert result["status"] == "BLOCKED"
    assert Path(result["markdown"]).exists()
    assert Path(result["jsonl"]).exists()
    assert Path(result["jsonl"]).read_text(encoding="utf-8") == ""


def test_network_error_redaction_never_exposes_key():
    key = "abc-secret-123"
    raw = f"failed calling https://ua.jooble.org/api/{key} because DNS"
    redacted = api.redact_secret(raw, key)
    assert key not in redacted
    assert "[REDACTED]" in redacted


def test_all_browser_route_concepts_are_covered_by_api_query_text():
    config = api.load_config(ROOT / "sources" / "jooble-api.json")
    text = " ".join(query.keywords.casefold() for query in config["queries"])
    for term in ("angular", "react", "frontend", "front end", "typescript", "javascript", "full stack", "fullstack", "node.js", "nodejs", "nestjs", "ai developer", "ai engineer"):
        assert term in text


def test_perform_request_posts_json_and_parses_response(monkeypatch):
    config = api.load_config(ROOT / "sources" / "jooble-api.json")
    query = config["queries"][0]
    captured = {}

    class FakeHeaders(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    class FakeResponse:
        status = 200
        headers = FakeHeaders({"Content-Length": "220"})
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def getcode(self): return 200
        def read(self, _limit):
            payload = {
                "totalCount": 1,
                "jobs": [{
                    "id": 1, "title": "React Developer", "location": "Remote",
                    "snippet": "React TypeScript", "salary": "", "source": "jooble",
                    "type": "Full-time", "link": "https://ua.jooble.org/jdp/1",
                    "company": "X", "updated": "2026-09-21T08:00:00Z"
                }],
            }
            return json.dumps(payload).encode()

    monkeypatch.setattr(api, "reserve_request_slot", lambda: 1)
    monkeypatch.setattr(api, "mark_request_success", lambda: captured.setdefault("success", True))
    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return FakeResponse()
    monkeypatch.setattr(api, "urlopen", fake_urlopen)
    response = api.perform_request("secret-key", config, query)
    assert response.total_count == 1 and len(response.jobs) == 1
    assert captured["body"]["keywords"] == query.keywords
    assert captured["body"]["location"] == query.location
    assert captured["success"] is True


def test_403_error_does_not_echo_key(monkeypatch):
    from urllib.error import HTTPError
    config = api.load_config(ROOT / "sources" / "jooble-api.json")
    query = config["queries"][0]
    monkeypatch.setattr(api, "reserve_request_slot", lambda: 1)
    monkeypatch.setattr(api, "urlopen", lambda *a, **k: (_ for _ in ()).throw(HTTPError("https://ua.jooble.org/api/secret-key", 403, "Forbidden", {}, None)))
    with pytest.raises(api.ApiRunnerError) as exc:
        api.perform_request("secret-key", config, query)
    assert "secret-key" not in str(exc.value)
    assert "403" in str(exc.value)


def test_quota_soft_limit_fails_closed(monkeypatch, tmp_path):
    usage = tmp_path / "usage.json"
    usage.write_text(json.dumps({"schema_version": 1, "attempted": api.API_QUOTA_SOFT_LIMIT, "successful": 0}), encoding="utf-8")
    monkeypatch.setattr(api, "USAGE_PATH", usage)
    with pytest.raises(api.ApiRunnerError):
        api.reserve_request_slot()


def test_recent_normal_result_never_reuses_partial_watermark(monkeypatch, tmp_path):
    md = tmp_path / "partial.md"
    js = tmp_path / "partial.jsonl"
    md.write_text("partial", encoding="utf-8")
    js.write_text("", encoding="utf-8")
    watermark = tmp_path / "watermark.json"
    watermark.write_text(json.dumps({
        "status": "PARTIAL",
        "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "markdown": str(md),
        "jsonl": str(js),
    }), encoding="utf-8")
    monkeypatch.setattr(api, "WATERMARK_PATH", watermark)
    assert api.recent_normal_result() is None


def test_partial_run_does_not_create_reuse_watermark(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(api, "RUN_DIAGNOSTICS_DIR", tmp_path / "state" / "api-runs")
    monkeypatch.setattr(api, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(api, "SEEN_PATH", tmp_path / "state" / "api-seen.jsonl")
    monkeypatch.setattr(api, "USAGE_PATH", tmp_path / "state" / "api-usage.json")
    monkeypatch.setattr(api, "WATERMARK_PATH", tmp_path / "state" / "api-watermark.json")
    monkeypatch.setattr(api, "LOCK_PATH", tmp_path / "state" / "api-run.lock")
    monkeypatch.setattr(api, "load_api_key", lambda: "hidden")
    calls = {"n": 0}
    def fake_request(_key, _config, query):
        calls["n"] += 1
        if calls["n"] == 1:
            return api.ApiResponse(query=query, total_count=0, jobs=[])
        raise api.ApiRunnerError("provider unavailable")
    monkeypatch.setattr(api, "perform_request", fake_request)
    args = api.build_parser().parse_args(["run", "--force"])
    result = api.execute(args)
    assert result["status"] == "PARTIAL"
    assert not api.WATERMARK_PATH.exists()
