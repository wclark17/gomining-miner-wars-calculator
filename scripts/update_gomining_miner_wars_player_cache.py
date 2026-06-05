#!/usr/bin/env python3
"""Refresh per-league full Miner Wars player caches for search."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from argparse import ArgumentParser
from datetime import datetime, timezone
from pathlib import Path

from update_gomining_miner_wars_live_snapshot import API_ROOT, LEAGUES, fetch_all_pages


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT
DEFAULT_MAX_ROWS = 50000


def parse_args() -> tuple[Path, list[int], int]:
  parser = ArgumentParser(description="Refresh per-league full Miner Wars player cache JSON files.")
  parser.add_argument(
    "--output-dir",
    type=Path,
    default=DEFAULT_OUTPUT_DIR,
    help="Directory to write gomining-miner-wars-players-league-<id>.json files.",
  )
  parser.add_argument(
    "--league",
    action="append",
    type=int,
    help="League id to refresh. May be passed more than once. Defaults to all known leagues.",
  )
  parser.add_argument(
    "--max-rows",
    type=int,
    default=DEFAULT_MAX_ROWS,
    help="Maximum player rows to fetch per league.",
  )
  args = parser.parse_args()
  league_ids = args.league or sorted(int(value) for value in LEAGUES)
  return args.output_dir, league_ids, args.max_rows


def write_player_cache(output_dir: Path, league_id: int, calculated_at: str, max_rows: int) -> dict:
  user = fetch_all_pages("user-leaderboard/index", league_id, calculated_at, max_rows)
  payload = {
    "generatedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
    "calculatedAt": calculated_at,
    "source": API_ROOT,
    "leagueId": league_id,
    "leagueName": LEAGUES[str(league_id)],
    "user": user,
  }
  output_dir.mkdir(parents=True, exist_ok=True)
  output = output_dir / f"gomining-miner-wars-players-league-{league_id}.json"
  output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  return {
    "leagueId": league_id,
    "leagueName": LEAGUES[str(league_id)],
    "count": int(user.get("count") or 0),
    "participants": len(user.get("participants") or []),
    "output": str(output),
  }


def main() -> int:
  output_dir, league_ids, max_rows = parse_args()
  calculated_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
  results = []
  errors: dict[str, str] = {}
  for league_id in league_ids:
    try:
      results.append(write_player_cache(output_dir, league_id, calculated_at, max_rows))
    except (urllib.error.URLError, RuntimeError, TimeoutError) as exc:
      errors[str(league_id)] = str(exc)
    time.sleep(0.08)

  print(json.dumps({"results": results, "errors": errors}, indent=2))
  return 0 if results else 1


if __name__ == "__main__":
  raise SystemExit(main())
