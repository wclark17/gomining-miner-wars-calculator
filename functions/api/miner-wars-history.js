const API_ROOT = "https://api.gomining.com/api/nft-game";
const MAX_ROWS = 1000;
const LIMIT = 50;

const corsHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, OPTIONS",
  "access-control-allow-headers": "content-type",
  "cache-control": "public, max-age=300",
  "content-type": "application/json; charset=utf-8"
};

const json = (payload, status = 200) => new Response(JSON.stringify(payload), {
  status,
  headers: corsHeaders
});

async function postGomining(path, body) {
  const response = await fetch(`${API_ROOT}/${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "user-agent": "gomining-miner-wars-calculator/1.0"
    },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(`GoMining ${path} returned ${response.status}`);
  const payload = await response.json();
  if (!payload || !payload.data) throw new Error(`GoMining ${path} returned no data`);
  return payload.data;
}

function rowKey(row, type) {
  if (type === "user") {
    const user = row.user || {};
    return user.userId || `${row.position}:${user.alias || ""}`;
  }
  const clan = row.clan || {};
  return row.clanId || `${row.position}:${clan.name || ""}`;
}

function mergeLeaderboardPages(path, pages) {
  const base = { ...pages[0] };
  if (path.includes("user-leaderboard")) {
    const seen = new Set();
    base.participants = pages.flatMap(page => page.participants || []).filter(row => {
      const key = rowKey(row, "user");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    return base;
  }

  for (const key of ["clansPromoted", "clansRemaining", "clansRelegated"]) {
    const seen = new Set();
    base[key] = pages.flatMap(page => page[key] || []).filter(row => {
      const dedupeKey = rowKey(row, "clan");
      if (seen.has(dedupeKey)) return false;
      seen.add(dedupeKey);
      return true;
    });
  }
  return base;
}

async function fetchAllPages(path, leagueId, calculatedAt) {
  const pages = [];
  let count = null;
  for (let skip = 0; count === null || skip < Math.min(count, MAX_ROWS); skip += LIMIT) {
    const page = await postGomining(path, {
      calculatedAt,
      pagination: { skip, limit: LIMIT },
      leagueId
    });
    pages.push(page);
    count = Number(page.count || 0);
    if (count === 0) break;
  }
  return mergeLeaderboardPages(path, pages);
}

export async function onRequestOptions() {
  return new Response(null, { headers: corsHeaders });
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const leagueId = Number.parseInt(url.searchParams.get("leagueId") || "", 10);
  const calculatedAt = url.searchParams.get("calculatedAt") || "";

  if (!Number.isInteger(leagueId) || leagueId <= 0) {
    return json({ error: "leagueId must be a positive integer" }, 400);
  }
  if (!Number.isFinite(Date.parse(calculatedAt))) {
    return json({ error: "calculatedAt must be an ISO timestamp" }, 400);
  }

  try {
    const [clan, user] = await Promise.all([
      fetchAllPages("clan-leaderboard/index-v2", leagueId, calculatedAt),
      fetchAllPages("user-leaderboard/index", leagueId, calculatedAt)
    ]);
    return json({
      generatedAt: new Date().toISOString(),
      calculatedAt,
      leagueId,
      source: "historical GoMining API",
      clan,
      user
    });
  } catch (error) {
    return json({ error: error.message || "Could not fetch historical Miner Wars data" }, 502);
  }
}
