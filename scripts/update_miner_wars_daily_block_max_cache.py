#!/usr/bin/env python3
"""Update daily max Miner Wars block-size observations for the current cycle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from update_miner_wars_cycle_summary_cache import (
    CYCLE_ANCHOR_NUMBER,
    CYCLE_ANCHOR_START_UTC,
    DEFAULT_OUTPUT as SUMMARY_OUTPUT,
    fetch_cycle,
    iso_z,
)


DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "miner-wars-daily-block-max.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def index_days(days: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    indexed = {}
    for day in days:
        date = str(day.get("date") or "")
        cycle = int(day.get("cycleNumber") or 0)
        if date and cycle:
            indexed[(date, cycle)] = day
    return indexed


def summary_index(summaries: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {
        int(summary["leagueId"]): dict(summary)
        for summary in summaries
        if "leagueId" in summary
    }


def update_max(existing: dict[str, Any] | None, snapshot: dict[str, Any], key: str, prefix: str, observed_at: str) -> dict[str, Any]:
    current_value = snapshot.get(key)
    previous = dict(existing or {})
    previous_value = previous.get(f"max{prefix}BlockSize")
    if current_value is None:
        return previous
    if previous_value is not None and float(previous_value) >= float(current_value):
        return previous
    return {
        f"max{prefix}BlockSize": current_value,
        f"max{prefix}BlockSizeAt": observed_at,
        f"{prefix[0].lower() + prefix[1:]}FundAtMax": snapshot.get(f"{prefix.lower()}Fund"),
        "blocksAtMax": snapshot.get("blocks"),
        "totalPowerAtMax": snapshot.get("totalPower"),
        "weightedEnergyEfficiencyPerThAtMax": snapshot.get("weightedEnergyEfficiencyPerTh"),
    }


def merge_daily_max(cache: dict[str, Any], cycle: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    calculated_at = cycle["calculatedAt"]
    date = calculated_at[:10]
    cycle_number = int(cycle["cycleNumber"])
    days = index_days(cache.get("days", []))
    changed = False
    day = days.get((date, cycle_number), {
        "date": date,
        "cycleNumber": cycle_number,
        "calculatedAtFirstSeen": calculated_at,
        "summaries": [],
    })
    if "calculatedAtLastSeen" not in day:
        day["calculatedAtLastSeen"] = calculated_at
        changed = True

    existing = summary_index(day.get("summaries", []))
    for snapshot in cycle.get("summaries", []):
        league_id = int(snapshot["leagueId"])
        row = existing.get(league_id, {
            "leagueId": league_id,
            "leagueName": snapshot.get("leagueName"),
        })
        before = json.dumps(row, sort_keys=True)
        row.update(update_max(row, snapshot, "btcBlockSize", "Btc", calculated_at))
        row.update(update_max(row, snapshot, "gmtBlockSize", "Gmt", calculated_at))
        if json.dumps(row, sort_keys=True) != before:
            day["calculatedAtLastSeen"] = calculated_at
            changed = True
        existing[league_id] = row

    day["summaries"] = [existing[key] for key in sorted(existing)]
    days[(date, cycle_number)] = day
    cache["days"] = [days[key] for key in sorted(days)]
    return cache, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle", type=int, help="Cycle number to snapshot. Defaults to the current cycle.")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=SUMMARY_OUTPUT)
    parser.add_argument("--skip-summary-cache", action="store_true")
    args = parser.parse_args()

    cycle_number = args.cycle
    if cycle_number is None:
        from update_miner_wars_cycle_summary_cache import current_cycle_number
        cycle_number = current_cycle_number()

    cycle = fetch_cycle(cycle_number, max(1, args.workers))
    cache = load_json(args.output)
    cache.update({
        "cycleAnchorNumber": CYCLE_ANCHOR_NUMBER,
        "cycleAnchorStart": iso_z(CYCLE_ANCHOR_START_UTC),
        "source": "GoMining API daily max observations",
    })
    cache, changed = merge_daily_max(cache, cycle)
    if changed or "generatedAt" not in cache:
        cache["generatedAt"] = iso_z(datetime.now(timezone.utc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if changed or not args.output.exists():
        args.output.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.skip_summary_cache:
        summary_cache = load_json(args.summary_output)
        existing_cycles = {
            int(item["cycleNumber"]): item
            for item in summary_cache.get("cycles", [])
            if "cycleNumber" in item
        }
        existing_cycles[cycle_number] = cycle
        summary_cache.update({
            "generatedAt": iso_z(datetime.now(timezone.utc)),
            "cycleAnchorNumber": CYCLE_ANCHOR_NUMBER,
            "cycleAnchorStart": iso_z(CYCLE_ANCHOR_START_UTC),
        })
        summary_cache["cycles"] = [existing_cycles[key] for key in sorted(existing_cycles)]
        args.summary_output.write_text(json.dumps(summary_cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    errors = sum(len(day.get("errors", {})) for day in cache.get("days", []))
    print(json.dumps({
        "cycleNumber": cycle_number,
        "calculatedAt": cycle["calculatedAt"],
        "dailyMaxOutput": str(args.output),
        "summaryOutput": None if args.skip_summary_cache else str(args.summary_output),
        "leagueCount": len(cycle.get("summaries", [])),
        "errors": errors,
        "changed": changed,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
