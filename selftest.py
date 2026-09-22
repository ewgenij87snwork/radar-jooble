#!/usr/bin/env python3
from __future__ import annotations
import hashlib, importlib.util, json, py_compile, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def fail(msg: str) -> None:
    raise SystemExit(f"SELFTEST FAIL: {msg}")

def check(cond: bool, msg: str) -> None:
    if not cond: fail(msg)

def main() -> None:
    py_compile.compile(str(ROOT / "api-runner.py"), doraise=True)
    py_compile.compile(str(ROOT / "radar.py"), doraise=True)
    node = shutil.which("node")
    if node:
        for rel in ("browser-runner.mjs", "sources/jooble-adapter.mjs"):
            subprocess.run([node, "--check", str(ROOT / rel)], check=True, stdout=subprocess.DEVNULL)
    bash = shutil.which("bash")
    if bash:
        subprocess.run([bash, "-n", str(ROOT / "run.command")], check=True, stdout=subprocess.DEVNULL)

    expected = {
        "radar.py": "f3b61c16ec0cece2381931040d660838729e120829d44745b262a48ccb07e6a0",
        "browser-runner.mjs": "665969a7bdf35e12b51889e57c40706a34673279d9f13778fcd0bd358b152a67",
        "sources/jooble-adapter.mjs": "3625a3459af5be8a2373dace5b5688af1707ca12bcf24c6b5b23ccd78eedaf51",
    }
    for rel, digest in expected.items():
        check(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == digest, f"browser baseline hash drift: {rel}")

    spec = importlib.util.spec_from_file_location("radar_api_selftest", ROOT / "api-runner.py")
    mod = importlib.util.module_from_spec(spec); sys.modules[spec.name] = mod; spec.loader.exec_module(mod)
    normal_args = mod.build_parser().parse_args(["run"])
    force_args = mod.build_parser().parse_args(["run", "--force"])
    check(mod.should_suppress_seen(normal_args, None), "normal run must suppress unchanged seen jobs")
    check(not mod.should_suppress_seen(force_args, None), "--force must return a full current snapshot")

    with tempfile.TemporaryDirectory(prefix="radar-jooble-selftest-") as td:
        base = Path(td)
        mod.RESULTS_DIR = base / "results"
        mod.TEST_RESULTS_DIR = base / "results" / "test" / "api"
        mod.STATE_DIR = base / "state"
        mod.RUN_DIAGNOSTICS_DIR = base / "state" / "api-runs"
        mod.SEEN_PATH = base / "state" / "api-seen.jsonl"
        mod.USAGE_PATH = base / "state" / "api-usage.json"
        mod.WATERMARK_PATH = base / "state" / "api-watermark.json"
        mod.LOCK_PATH = base / "state" / "api-run.lock"
        args = mod.build_parser().parse_args(["run", "--fixture", str(ROOT / "tests/fixtures/jooble-api-response.json")])
        result = mod.execute(args)
        check(result["status"] == "DONE", "fixture run did not finish DONE")
        md, js = Path(result["markdown"]), Path(result["jsonl"])
        check(md.exists() and js.exists(), "fixture run did not create both user files")
        rows = [json.loads(line) for line in js.read_text(encoding="utf-8").splitlines() if line.strip()]
        check(rows, "fixture JSONL is empty")
        check(all(r.get("decision") in {"MATCH", "REVIEW"} for r in rows), "REJECT leaked to user JSONL")
        check(any(r.get("work_mode") == "HYBRID" for r in rows), "hybrid lane missing")
        check(any(r.get("work_mode") == "UNKNOWN" and r.get("decision") == "REVIEW" for r in rows), "unknown work mode was dropped")

    # A local .env.local is required for normal authenticated use. Its presence is
    # not a distribution failure; the invariant is that Git ignores and does not
    # track it. Never read or print the file contents here.
    gitignore_lines = {
        line.strip()
        for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    check(".env.local" in gitignore_lines, ".env.local must be ignored by git")
    check("state/api-seen.jsonl" not in gitignore_lines, "api-seen history must be git-syncable")
    check("state/api-usage.json" not in gitignore_lines, "api quota state must be git-syncable")
    launcher = (ROOT / "run.command").read_text(encoding="utf-8")
    check("api-runner.py run --freshness 24h --force" in launcher, "launcher must run a forced 24h snapshot")
    check("git add -f -- \"$item\"" in launcher, "launcher must archive the current result pair")

    git = shutil.which("git")
    if git and (ROOT / ".git").exists():
        ignored = subprocess.run(
            [git, "-C", str(ROOT), "check-ignore", "-q", "--", ".env.local"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        check(ignored.returncode == 0, ".env.local is not ignored by git")

        tracked = subprocess.run(
            [git, "-C", str(ROOT), "ls-files", "--error-unmatch", "--", ".env.local"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        check(tracked.returncode != 0, ".env.local must never be tracked")

    print("SELFTEST PASS")

if __name__ == "__main__":
    main()
