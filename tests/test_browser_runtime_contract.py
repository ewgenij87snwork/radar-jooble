from pathlib import Path
import hashlib
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_preserved_browser_runtime_exact_hashes():
    expected = {
        "radar.py": "f3b61c16ec0cece2381931040d660838729e120829d44745b262a48ccb07e6a0",
        "browser-runner.mjs": "665969a7bdf35e12b51889e57c40706a34673279d9f13778fcd0bd358b152a67",
        "sources/jooble-adapter.mjs": "3625a3459af5be8a2373dace5b5688af1707ca12bcf24c6b5b23ccd78eedaf51",
    }
    for rel, digest in expected.items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest


def test_exactly_thirteen_browser_production_routes():
    spec = importlib.util.spec_from_file_location("radar_browser_contract", ROOT / "radar.py")
    runtime = importlib.util.module_from_spec(spec)
    sys.modules["radar_browser_contract"] = runtime
    spec.loader.exec_module(runtime)
    assert len(runtime.SOURCE_ROUTES["Jooble"]) == 13


def test_browser_fallback_is_explicit_and_uses_existing_surface():
    text = (ROOT / "BROWSER-FALLBACK.md").read_text(encoding="utf-8")
    assert "surface.family === \"chrome\"" in text
    assert "realpathSync(\".\")" in text
    assert "--freshness" in text


def test_browser_adapter_stays_portable():
    adapter = (ROOT / "sources" / "jooble-adapter.mjs").read_text(encoding="utf-8")
    for forbidden in ("radar.py", "results/", "state/", "RADAR-FAST", "/Users/"):
        assert forbidden not in adapter
