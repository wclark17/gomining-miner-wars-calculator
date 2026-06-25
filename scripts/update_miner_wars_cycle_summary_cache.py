#!/usr/bin/env python3
"""Build a static Miner Wars cycle summary cache for completed cycles."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_ROOT = "https://api.gomining.com/api/nft-game"
CYCLE_ANCHOR_NUMBER = 148
CYCLE_ANCHOR_START_UTC = datetime(2026, 6, 16, tzinfo=timezone.utc)
SECONDS_PER_WEEK = 7 * 24 * 60 * 60
DEFAULT_START_CYCLE = 111
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "miner-wars-cycle-summaries.json"
ROMAN = [
    "I",
    "II",
    "III",
    "IV",
    "V",
    "VI",
    "VII",
    "VIII",
    "IX",
    "X",
    "XI",
    "XII",
    "XIII",
    "XIV",
    "XV",
    "XVI",
    "XVII",
    "XVIII",
    "XIX",
    "XX",
    "XXI",
    "XXII",
    "XXIII",
    "XXIV",
    "XXV",
    "XXVI",
]
BASE_LEAGUES = {1: "Odyssey", 2: "League 2", 3: "Horizon", 4: "Eclipse"}
MIN_DUNE_COUNT = 27


def to_roman(value: int) -> str:
    table = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    remaining = value
    result = ""
    for number, symbol in table:
        while remaining >= number:
            result += symbol
            remaining -= number
    return result


def league_name(league_id: int) -> str:
    if league_id in BASE_LEAGUES:
        return BASE_LEAGUES[league_id]
    if league_id >= 5:
        return f"Dune {to_roman(league_id - 4)}"
    return f"League {league_id}"


LEAGUES = {league_id: league_name(league_id) for league_id in range(1, 5 + MIN_DUNE_COUNT)}


def iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def current_cycle_number(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    elapsed = int((now - CYCLE_ANCHOR_START_UTC).total_seconds() // SECONDS_PER_WEEK)
    return CYCLE_ANCHOR_NUMBER + elapsed


def cycle_bounds(cycle_number: int) -> tuple[datetime, datetime]:
    offset = cycle_number - CYCLE_ANCHOR_NUMBER
    start_ts = CYCLE_ANCHOR_START_UTC.timestamp() + offset * SECONDS_PER_WEEK
    start = datetime.fromtimestamp(start_ts, timezone.utc)
    end = datetime.fromtimestamp(start_ts + SECONDS_PER_WEEK, timezone.utc)
    return start, end


def cycle_calculated_at(cycle_number: int, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    if cycle_number >= current_cycle_number(now):
        return iso_z(now)
    _start, end = cycle_bounds(cycle_number)
    return iso_z(datetime.fromtimestamp(end.timestamp() - 1, timezone.utc))


def post_gomining(path: str, league_id: int, calculated_at: str) -> dict[str, Any]:
    body = {
        "calculatedAt": calculated_at,
        "leagueId": league_id,
        "pagination": {"skip": 0, "limit": 1},
    }
    request = urllib.request.Request(
        f"{API_ROOT}/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", "user-agent": "gomining-cycle-summary-cache/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "data" not in payload:
        raise RuntimeError(f"{path} league {league_id} returned no data")
    return payload["data"]


def has_league_data(summary: dict[str, Any]) -> bool:
    return any(float(summary.get(key) or 0) > 0 for key in ("blocks", "totalPower", "btcFund", "gmtFund"))


def fetch_league_summary(
    cycle_number: int,
    league_id: int,
    calculated_at: str,
    leagues: dict[int, str] | None = None,
) -> dict[str, Any]:
    leagues = leagues or LEAGUES
    clan = post_gomining("clan-leaderboard/index-v2", league_id, calculated_at)
    user = post_gomining("user-leaderboard/index", league_id, calculated_at)
    clan_blocks = float(clan.get("totalMinedBlocks") or 0)
    user_blocks = float(user.get("totalMinedBlocks") or 0)
    btc_fund = float(clan.get("btcFund") or 0)
    gmt_fund = float(user.get("gmtFund") or 0)
    return {
        "leagueId": league_id,
        "leagueName": leagues.get(league_id, league_name(league_id)),
        "btcFund": btc_fund,
        "gmtFund": gmt_fund,
        "blocks": clan_blocks or user_blocks or 0,
        "clanBlocks": clan_blocks,
        "userBlocks": user_blocks,
        "btcBlockSize": btc_fund / clan_blocks if clan_blocks > 0 else None,
        "gmtBlockSize": gmt_fund / user_blocks if user_blocks > 0 else None,
        "totalPower": float(clan.get("totalPower") or 0),
        "weightedEnergyEfficiencyPerTh": float(clan.get("weightedEnergyEfficiencyPerTh") or 0),
    }


def discover_leagues(calculated_at: str, max_league: int = 80, empty_stop: int = 5) -> dict[int, str]:
    leagues = dict(LEAGUES)
    empty_run = 0
    for league_id in range(1, max_league + 1):
        if league_id in BASE_LEAGUES:
            continue
        try:
            summary = fetch_league_summary(0, league_id, calculated_at, leagues)
        except Exception:  # noqa: BLE001 - discovery should not block known leagues.
            empty_run += 1
        else:
            if has_league_data(summary):
                leagues[league_id] = league_name(league_id)
                empty_run = 0
            elif league_id >= 5 + MIN_DUNE_COUNT:
                empty_run += 1
        if league_id >= 5 + MIN_DUNE_COUNT and empty_run >= empty_stop:
            break
    return {league_id: leagues[league_id] for league_id in sorted(leagues)}


def fetch_cycle(cycle_number: int, max_workers: int, leagues: dict[int, str] | None = None) -> dict[str, Any]:
    calculated_at = cycle_calculated_at(cycle_number)
    leagues = leagues or discover_leagues(calculated_at)
    start, end = cycle_bounds(cycle_number)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_league_summary, cycle_number, league_id, calculated_at, leagues): league_id
            for league_id in sorted(leagues)
        }
        summaries = []
        errors = {}
        for future in concurrent.futures.as_completed(futures):
            league_id = futures[future]
            try:
                summaries.append(future.result())
            except Exception as exc:  # noqa: BLE001 - preserve per-league failures in the cache.
                errors[str(league_id)] = str(exc)
        summaries.sort(key=lambda item: item["leagueId"])
    return {
        "cycleNumber": cycle_number,
        "start": iso_z(start),
        "end": iso_z(end),
        "calculatedAt": calculated_at,
        "summaries": summaries,
        "errors": errors,
    }


def load_existing(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-cycle", type=int, default=DEFAULT_START_CYCLE)
    parser.add_argument("--end-cycle", type=int, default=current_cycle_number() - 1)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-league-scan", type=int, default=80)
    parser.add_argument("--empty-league-stop", type=int, default=5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    leagues = discover_leagues(
        cycle_calculated_at(current_cycle_number()),
        max_league=args.max_league_scan,
        empty_stop=args.empty_league_stop,
    )

    existing = load_existing(args.output)
    existing_cycles = {
        int(cycle["cycleNumber"]): cycle
        for cycle in existing.get("cycles", [])
        if "cycleNumber" in cycle
    }

    cycles = dict(existing_cycles)
    for cycle_number in range(args.start_cycle, args.end_cycle + 1):
        existing_cycle = existing_cycles.get(cycle_number)
        existing_ids = {int(summary["leagueId"]) for summary in existing_cycle.get("summaries", [])} if existing_cycle else set()
        if not args.force and existing_cycle and existing_ids.issuperset(leagues):
            cycles[cycle_number] = existing_cycle
            continue
        print(f"fetching cycle {cycle_number}", flush=True)
        cycles[cycle_number] = fetch_cycle(cycle_number, max(1, args.workers), leagues)
        time.sleep(0.15)

    payload = {
        "generatedAt": iso_z(datetime.now(timezone.utc)),
        "source": API_ROOT,
        "cycleAnchorNumber": CYCLE_ANCHOR_NUMBER,
        "cycleAnchorStart": iso_z(CYCLE_ANCHOR_START_UTC),
        "leagues": [{"leagueId": league_id, "leagueName": name} for league_id, name in sorted(leagues.items())],
        "cycles": [cycles[key] for key in sorted(cycles)],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {len(payload['cycles'])} cycles to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
