const API_ROOT = "https://api.gomining.com/api/nft-game";
const LIMIT = 1;
const CONCURRENCY = 2;

const ROMAN = [
  "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
  "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
  "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI"
];

const LEAGUES = new Map([
  [1, "Odyssey"],
  [2, "League 2"],
  [3, "Horizon"],
  [4, "Eclipse"],
  ...ROMAN.map((roman, index) => [index + 5, `Dune ${roman}`])
]);

const baseHeaders = {
  "access-control-allow-origin": "*",
  "access-control-allow-methods": "GET, OPTIONS",
  "access-control-allow-headers": "content-type",
  "content-type": "application/json; charset=utf-8"
};

const cacheHeaders = calculatedAt => {
  const ageMs = Date.now() - Date.parse(calculatedAt);
  const maxAge = ageMs > 10 * 60 * 1000 ? 31536000 : 300;
  return {
    ...baseHeaders,
    "cache-control": `public, max-age=${maxAge}${maxAge > 300 ? ", immutable" : ""}`
  };
};

const json = (payload, status = 200, headers = cacheHeaders(new Date().toISOString())) => new Response(JSON.stringify(payload), {
  status,
  headers
});

async function postGomining(path, leagueId, calculatedAt) {
  const response = await fetch(`${API_ROOT}/${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "user-agent": "gomining-miner-wars-calculator/1.0"
    },
    body: JSON.stringify({
      calculatedAt,
      leagueId,
      pagination: { skip: 0, limit: LIMIT }
    })
  });
  if (!response.ok) throw new Error(`GoMining ${path} for league ${leagueId} returned ${response.status}`);
  const payload = await response.json();
  if (!payload || !payload.data) throw new Error(`GoMining ${path} for league ${leagueId} returned no data`);
  return payload.data;
}

async function fetchLeagueSummary(leagueId, calculatedAt) {
  const [clan, user] = await Promise.all([
    postGomining("clan-leaderboard/index-v2", leagueId, calculatedAt),
    postGomining("user-leaderboard/index", leagueId, calculatedAt)
  ]);
  const clanBlocks = Number(clan.totalMinedBlocks || 0);
  const userBlocks = Number(user.totalMinedBlocks || 0);
  const btcFund = Number(clan.btcFund || 0);
  const gmtFund = Number(user.gmtFund || 0);
  return {
    leagueId,
    leagueName: LEAGUES.get(leagueId) || `League ${leagueId}`,
    calculatedAt,
    btcFund,
    gmtFund,
    blocks: clanBlocks || userBlocks || 0,
    clanBlocks,
    userBlocks,
    btcBlockSize: clanBlocks > 0 ? btcFund / clanBlocks : null,
    gmtBlockSize: userBlocks > 0 ? gmtFund / userBlocks : null,
    totalPower: Number(clan.totalPower || 0),
    weightedEnergyEfficiencyPerTh: Number(clan.weightedEnergyEfficiencyPerTh || 0)
  };
}

async function fetchLeagueSummarySafe(leagueId, calculatedAt) {
  try {
    return { summary: await fetchLeagueSummary(leagueId, calculatedAt) };
  } catch (error) {
    return {
      error: {
        leagueId,
        leagueName: LEAGUES.get(leagueId) || `League ${leagueId}`,
        message: error.message || "Could not fetch league summary"
      }
    };
  }
}

async function mapWithLimit(values, limit, mapper) {
  const results = new Array(values.length);
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, values.length) }, async () => {
    while (next < values.length) {
      const index = next;
      next += 1;
      results[index] = await mapper(values[index]);
    }
  });
  await Promise.all(workers);
  return results;
}

export async function onRequestOptions() {
  return new Response(null, { headers: cacheHeaders(new Date().toISOString()) });
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const calculatedAt = url.searchParams.get("calculatedAt") || "";
  const leagueParam = url.searchParams.get("leagueId") || "all";

  if (!Number.isFinite(Date.parse(calculatedAt))) {
    return json({ error: "calculatedAt must be an ISO timestamp" }, 400);
  }

  let leagueIds;
  if (leagueParam === "all") {
    leagueIds = [...LEAGUES.keys()];
  } else {
    const leagueId = Number.parseInt(leagueParam, 10);
    if (!Number.isInteger(leagueId) || leagueId <= 0) {
      return json({ error: "leagueId must be a positive integer or all" }, 400);
    }
    leagueIds = [leagueId];
  }

  try {
    const cache = typeof caches !== "undefined" ? caches.default : null;
    if (cache) {
      const cached = await cache.match(request);
      if (cached) return cached;
    }

    const results = await mapWithLimit(leagueIds, CONCURRENCY, leagueId => fetchLeagueSummarySafe(leagueId, calculatedAt));
    const summaries = results.map(result => result.summary).filter(Boolean);
    const errors = Object.fromEntries(
      results
        .map(result => result.error)
        .filter(Boolean)
        .map(error => [String(error.leagueId), error])
    );
    if (!summaries.length) {
      const messages = Object.values(errors).map(error => error.message).filter(Boolean);
      throw new Error(messages[0] || "No league summaries returned");
    }
    const response = json({
      generatedAt: new Date().toISOString(),
      calculatedAt,
      source: "GoMining API summary",
      summaries,
      errors
    }, 200, cacheHeaders(calculatedAt));
    if (cache) {
      await cache.put(request, response.clone());
    }
    return response;
  } catch (error) {
    return json({ error: error.message || "Could not fetch Miner Wars cycle summary" }, 502);
  }
}
