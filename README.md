# GoMining Miner Wars Calculator

Static Miner Wars vs solo mining calculator for Tuesday-to-Tuesday UTC cycles.

## Cloudflare Pages

- Framework preset: none
- Build command: none
- Output directory: `/`

The page can run from the bundled `gomining-miner-wars-live.json` snapshot, but the intended public setup is to point `config.js` at a live snapshot endpoint:

```js
window.MINER_WARS_SNAPSHOT_API = "https://<snapshot-host>/v1/gomining/miner-wars-live.json";
window.MINER_WARS_PLAYER_CACHE_BASE = "https://<snapshot-host>/v1/gomining";
```

The calculator will try that endpoint first and fall back to the bundled JSON if the endpoint is unavailable.

Past-cycle loading uses the Cloudflare Pages Function at `/api/miner-wars-history`.
Cycle 148 is anchored to Tuesday 2026-06-16 00:00 UTC; later/current cycle numbers are derived from that anchor.

## Snapshot Refresh

Refresh the bundled snapshot locally:

```bash
python3 scripts/update_gomining_miner_wars_live_snapshot.py
```

Refresh a deployed server-side JSON file:

```bash
python3 scripts/update_gomining_miner_wars_live_snapshot.py --output /path/to/gomining-miner-wars-live.json
```

Refresh the slower full player search cache:

```bash
python3 scripts/update_gomining_miner_wars_player_cache.py --output-dir /path/to/public
```

This writes one `gomining-miner-wars-players-league-<id>.json` file per league. The calculator fetches only the selected league's player cache so the first page load stays small.

## Files

- `index.html` - calculator
- `gomining-miner-wars-help.html` - help page
- `config.js` - optional public snapshot endpoint
- `functions/api/miner-wars-history.js` - same-origin historical leaderboard proxy
- `gomining-miner-wars-live.json` - fallback snapshot
- `scripts/update_gomining_miner_wars_live_snapshot.py` - snapshot refresh script
- `scripts/update_gomining_miner_wars_player_cache.py` - slower full player search cache refresh script
