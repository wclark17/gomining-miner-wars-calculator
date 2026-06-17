#!/usr/bin/env python3
"""Refresh static Miner Wars leaderboard data for the calculator."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUTS = [ROOT / "gomining-miner-wars-live.json"]
API_ROOT = "https://api.gomining.com/api/nft-game"
MAX_ROWS_PER_LEAGUE = 1000
FULL_SNAPSHOT_LEAGUES = {19}
LEAGUES = {
    "1": "Odyssey",
    "2": "League 2",
    "3": "Horizon",
    "4": "Eclipse",
}
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
    "XXVII",
]
for index, roman in enumerate(ROMAN, start=1):
    LEAGUES[str(index + 4)] = f"Dune {roman}"


def post(path: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"{API_ROOT}/{path}",
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json", "user-agent": "daneel-mission-control/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if "data" not in payload:
        raise RuntimeError(f"{path} returned no data")
    return payload["data"]


def merge_leaderboard_pages(path: str, pages: list[dict]) -> dict:
    base = dict(pages[0])
    if "user-leaderboard" in path:
        seen = set()
        participants = []
        for page in pages:
            for participant in page.get("participants", []):
                user = participant.get("user") or {}
                key = user.get("userId") or f"{participant.get('position')}:{user.get('alias', '')}"
                if key in seen:
                    continue
                seen.add(key)
                participants.append(participant)
        base["participants"] = participants
        return base

    for rows_key in ("clansPromoted", "clansRemaining", "clansRelegated"):
        seen = set()
        rows = []
        for page in pages:
            for row in page.get(rows_key, []):
                clan = row.get("clan") or {}
                key = row.get("clanId") or f"{row.get('position')}:{clan.get('name', '')}"
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
        base[rows_key] = rows
    return base


def fetch_all_pages(path: str, league_id: int, calculated_at: str, row_cap: int) -> dict:
    limit = 50
    pages = []
    skip = 0
    count = None
    while count is None or skip < min(count, row_cap):
        body = {
            "calculatedAt": calculated_at,
            "pagination": {"skip": skip, "limit": limit},
            "leagueId": league_id,
        }
        page = post(path, body)
        pages.append(page)
        count = int(page.get("count") or 0)
        skip += limit
        if count == 0:
            break
    return merge_leaderboard_pages(path, pages)


def fetch_league(league_id: int, calculated_at: str) -> dict:
    row_cap = MAX_ROWS_PER_LEAGUE if league_id in FULL_SNAPSHOT_LEAGUES else 50
    return {
        "name": LEAGUES[str(league_id)],
        "clan": fetch_all_pages("clan-leaderboard/index-v2", league_id, calculated_at, row_cap),
        "user": fetch_all_pages("user-leaderboard/index", league_id, calculated_at, row_cap),
    }


def parse_args() -> list[Path]:
    parser = ArgumentParser(description="Refresh static Miner Wars leaderboard data for the calculator.")
    parser.add_argument(
        "--output",
        action="append",
        type=Path,
        help="Snapshot JSON output path. May be passed more than once.",
    )
    args = parser.parse_args()
    return args.output or DEFAULT_OUTPUTS


def main() -> int:
    outputs = parse_args()
    calculated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    leagues: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for league_id in sorted(int(value) for value in LEAGUES):
        try:
            leagues[str(league_id)] = fetch_league(league_id, calculated_at)
        except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
            errors[str(league_id)] = str(exc)
        time.sleep(0.08)

    payload = {
        "generatedAt": calculated_at,
        "source": API_ROOT,
        "leagues": leagues,
        "errors": errors,
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    for output in outputs:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(f"wrote {len(leagues)} leagues to {', '.join(str(path) for path in outputs)}")
    if errors:
        print(f"errors: {errors}")
    return 0 if leagues else 1


if __name__ == "__main__":
    raise SystemExit(main())
