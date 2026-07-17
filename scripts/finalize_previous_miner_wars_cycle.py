#!/usr/bin/env python3
"""Publish the previous completed Miner Wars cycle after strict validation."""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from update_miner_wars_cycle_summary_cache import current_cycle_number, has_league_data


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "miner-wars-cycle-summaries.json"
PUBLIC_CACHE_URL = "https://minerwars.clark5.net/data/miner-wars-cycle-summaries.json"
MIN_POPULATED_LEAGUES = 25
DEPLOY_TIMEOUT_SECONDS = 240


def run(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )


def load_cache(raw: bytes | None = None) -> dict:
    return json.loads(raw.decode("utf-8") if raw is not None else CACHE.read_text(encoding="utf-8"))


def cycle_from(cache: dict, cycle_number: int) -> dict | None:
    return next(
        (cycle for cycle in cache.get("cycles", []) if int(cycle.get("cycleNumber", -1)) == cycle_number),
        None,
    )


def validate_cycle(cache: dict, cycle_number: int) -> dict:
    cycle = cycle_from(cache, cycle_number)
    if not cycle:
        raise RuntimeError(f"cycle {cycle_number} is absent from the summary cache")

    expected_ids = {int(item["leagueId"]) for item in cache.get("leagues", [])}
    actual_ids = {int(item["leagueId"]) for item in cycle.get("summaries", [])}
    missing = sorted(expected_ids - actual_ids)
    errors = cycle.get("errors", {})
    populated = sum(has_league_data(summary) for summary in cycle.get("summaries", []))

    if errors:
        raise RuntimeError(f"cycle {cycle_number} contains API errors: {errors}")
    if missing:
        raise RuntimeError(f"cycle {cycle_number} is missing league ids: {missing}")
    if populated < MIN_POPULATED_LEAGUES:
        raise RuntimeError(
            f"cycle {cycle_number} has only {populated} populated leagues; data may not be final"
        )
    return cycle


def wait_for_deploy(cycle_number: int, expected_cycle: dict) -> None:
    deadline = time.monotonic() + DEPLOY_TIMEOUT_SECONDS
    last_error = "deployment not checked"
    while time.monotonic() < deadline:
        try:
            request = urllib.request.Request(
                f"{PUBLIC_CACHE_URL}?ts={int(time.time())}",
                headers={"user-agent": "Mozilla/5.0 MinerWarsCycleFinalizer/1.0"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                live = json.loads(response.read().decode("utf-8"))
            if cycle_from(live, cycle_number) == expected_cycle:
                return
            last_error = f"cycle {cycle_number} is not current in the deployed cache"
        except Exception as exc:  # noqa: BLE001 - retain the last deployment error for alerting.
            last_error = str(exc)
        time.sleep(10)
    raise RuntimeError(f"deployment verification timed out: {last_error}")


def main() -> int:
    status = run("git", "status", "--porcelain", capture=True).stdout.strip()
    if status:
        raise RuntimeError(f"refusing to run with a dirty worktree: {status}")

    completed_cycle = current_cycle_number() - 1
    original = CACHE.read_bytes()
    previous = cycle_from(load_cache(original), completed_cycle)

    try:
        run(
            sys.executable,
            "scripts/update_miner_wars_cycle_summary_cache.py",
            "--start-cycle",
            str(completed_cycle),
            "--end-cycle",
            str(completed_cycle),
            "--force",
        )
        refreshed_cache = load_cache()
        refreshed = validate_cycle(refreshed_cache, completed_cycle)
    except Exception:
        CACHE.write_bytes(original)
        raise

    if previous == refreshed:
        CACHE.write_bytes(original)
        print(f"NO_CHANGE: cycle {completed_cycle} is already finalized.")
        return 0

    run("git", "add", str(CACHE.relative_to(ROOT)))
    run("git", "commit", "-m", f"Finalize Miner Wars cycle {completed_cycle}")
    run("git", "push")
    wait_for_deploy(completed_cycle, refreshed)
    commit = run("git", "rev-parse", "--short", "HEAD", capture=True).stdout.strip()
    print(
        f"FINALIZED: cycle {completed_cycle}, {len(refreshed['summaries'])} leagues, "
        f"commit {commit}, deployment verified."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - cron needs one concise actionable failure.
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
