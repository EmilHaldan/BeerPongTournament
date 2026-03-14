/* ── Demo Data – Stub fetch() with fake teams & matches ────────────── */

(function () {
  const TEAMS = [
    { id: "t1", name: "The Chuggers", members: ["Emil", "Karl"] },
    { id: "t2", name: "Ball Busters", members: ["Anna", "Erik"] },
    { id: "t3", name: "Splash Bros", members: ["Oskar", "Liam"] },
    { id: "t4", name: "Cup Hunters", members: ["Sofia", "Nils"] },
    { id: "t5", name: "Pong Stars", members: ["Maja", "Axel", "Ida"] },
    { id: "t6", name: "Last Call", members: ["Freja", "Hugo"] },
  ];

  const MATCHES = [
    { id: "m1", team1_name: "The Chuggers", team2_name: "Ball Busters", team1_score: 6, team2_score: 3, heat: 1, created_at: "2026-03-14T18:05:00Z" },
    { id: "m2", team1_name: "Splash Bros", team2_name: "Cup Hunters", team1_score: 4, team2_score: 5, heat: 1, created_at: "2026-03-14T18:08:00Z" },
    { id: "m3", team1_name: "Pong Stars", team2_name: "Last Call", team1_score: 6, team2_score: 2, heat: 1, created_at: "2026-03-14T18:12:00Z" },
    { id: "m4", team1_name: "The Chuggers", team2_name: "Splash Bros", team1_score: 3, team2_score: 4, heat: 2, created_at: "2026-03-14T19:01:00Z" },
    { id: "m5", team1_name: "Ball Busters", team2_name: "Pong Stars", team1_score: 5, team2_score: 5, heat: 2, created_at: "2026-03-14T19:05:00Z" },
    { id: "m6", team1_name: "Cup Hunters", team2_name: "Last Call", team1_score: 6, team2_score: 1, heat: 2, created_at: "2026-03-14T19:10:00Z" },
  ];

  function buildLeaderboard() {
    const stats = {};
    TEAMS.forEach(t => {
      stats[t.name] = { team_name: t.name, total_wins: 0, total_loss: 0, total_score: 0, total_matches: 0 };
    });
    MATCHES.forEach(m => {
      const s1 = stats[m.team1_name];
      const s2 = stats[m.team2_name];
      if (!s1 || !s2) return;
      s1.total_matches++;
      s2.total_matches++;
      s1.total_score += m.team1_score;
      s2.total_score += m.team2_score;
      if (m.team1_score > m.team2_score) { s1.total_wins++; s2.total_loss++; }
      else if (m.team2_score > m.team1_score) { s2.total_wins++; s1.total_loss++; }
    });
    return Object.values(stats).sort((a, b) => b.total_wins - a.total_wins || b.total_score - a.total_score);
  }

  function buildHeatInfo() {
    return {
      current_heat: 2,
      timer_started_at: null,
      timer_duration: 600,
      matchups: [
        { team1_name: "The Chuggers", team2_name: "Splash Bros", team1_points: 3, team2_points: 2, team1_score: 3, team2_score: 4, recorded: true, winner: "Splash Bros" },
        { team1_name: "Ball Busters", team2_name: "Pong Stars", team1_points: 1, team2_points: 3, team1_score: 5, team2_score: 5, recorded: true, winner: null },
        { team1_name: "Cup Hunters", team2_name: "Last Call", team1_points: 2, team2_points: 0, team1_score: 6, team2_score: 1, recorded: true, winner: "Cup Hunters" },
      ],
      teams_recorded: ["The Chuggers", "Splash Bros", "Ball Busters", "Pong Stars", "Cup Hunters", "Last Call"],
      teams_not_recorded: [],
    };
  }

  const originalFetch = window.fetch;

  window.fetch = function (url, options) {
    const path = String(url).replace(/^https?:\/\/[^/]+/, "");

    if (path.endsWith("/leaderboard")) return jsonResponse(buildLeaderboard());
    if (path.endsWith("/teams/names")) return jsonResponse(TEAMS.map(t => t.name));
    if (path.endsWith("/teams") && (!options || options.method !== "DELETE")) return jsonResponse(TEAMS);
    if (path.endsWith("/matches") && (!options || options.method !== "DELETE")) return jsonResponse(MATCHES);
    if (path.match(/\/heat(\/|$)/) && (!options || !options.method || options.method === "GET")) return jsonResponse(buildHeatInfo());
    if (path.endsWith("/admin/verify")) return jsonResponse({ ok: true });

    // Fallback: return empty success for POST/DELETE
    if (options && (options.method === "POST" || options.method === "DELETE")) {
      return jsonResponse({ ok: true });
    }

    return jsonResponse({});
  };

  function jsonResponse(data) {
    return new Promise(resolve => {
      setTimeout(() => {
        resolve(new Response(JSON.stringify(data), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }));
      }, 10);
    });
  }
})();
