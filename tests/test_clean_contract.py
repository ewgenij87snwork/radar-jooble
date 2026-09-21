from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_start_contract_returns_exactly_two_user_outputs():
    start = (ROOT / "start.md").read_text(encoding="utf-8")
    assert "python3 api-runner.py run" in start
    assert "ровно два" in start.lower()
    assert "*.md" in start and "*.jsonl" in start
    assert "BROWSER-FALLBACK.md" in start


def test_env_is_excluded_from_clean_artifacts_contract():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert ".env.local" in ignore
    assert example.strip() == "JOOBLE_API_KEY="


def test_docs_preserve_browser_path_and_hybrid_lane():
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    api_doc = (ROOT / "sources" / "jooble-api.md").read_text(encoding="utf-8")
    assert "byte-for-byte" in agents
    assert "Hybrid" in api_doc and "eligible" in api_doc
    assert "BOUNDED_PAGE1" in agents
