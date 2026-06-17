#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 scripts/update_miner_wars_daily_block_max_cache.py --workers 4 --skip-summary-cache

if git diff --quiet -- data/miner-wars-daily-block-max.json; then
  echo "NO_CHANGE: Miner Wars daily max cache unchanged."
  exit 0
fi

git add data/miner-wars-daily-block-max.json
git commit -m "Update Miner Wars daily block maxima"
git push
