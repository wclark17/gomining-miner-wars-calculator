# GoMining Miner Wars Calculator

Static Miner Wars vs solo mining calculator for the current Tuesday-to-Tuesday UTC cycle.

## Cloudflare Pages

- Framework preset: none
- Build command: none
- Output directory: `/`

The page can run from the bundled `gomining-miner-wars-live.json` snapshot, but the intended public setup is to point `config.js` at a live snapshot endpoint:

```js
window.MINER_WARS_SNAPSHOT_API = "https://<snapshot-host>/v1/gomining/miner-wars-live.json";
```

The calculator will try that endpoint first and fall back to the bundled JSON if the endpoint is unavailable.

## Snapshot Refresh

Refresh the bundled snapshot locally:

```bash
python3 scripts/update_gomining_miner_wars_live_snapshot.py
```

Refresh a deployed server-side JSON file:

```bash
python3 scripts/update_gomining_miner_wars_live_snapshot.py --output /path/to/gomining-miner-wars-live.json
```

## Files

- `index.html` - calculator
- `gomining-miner-wars-help.html` - help page
- `config.js` - optional public snapshot endpoint
- `gomining-miner-wars-live.json` - fallback snapshot
- `scripts/update_gomining_miner_wars_live_snapshot.py` - snapshot refresh script
