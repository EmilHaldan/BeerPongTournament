/* ── Beer Pong Tournament – Frontend JS ────────────────────────────── */

// Tab switching
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((s) => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");

    // Auto-refresh when switching tabs
    if (btn.dataset.tab === "scoreboard") loadLeaderboard();
    if (btn.dataset.tab === "matches") loadMatches();
    if (btn.dataset.tab === "teams") loadTeams();
    if (btn.dataset.tab === "register") populateTeamDropdowns();
  });
});

// Error banner helper
function showError(msg) {
  const banner = document.getElementById("error-banner");
  banner.textContent = msg;
  banner.classList.remove("hidden");
  setTimeout(() => banner.classList.add("hidden"), 5000);
}

function showSuccess() {
  const el = document.getElementById("success-msg");
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3000);
}

// ── Leaderboard ──────────────────────────────────────────────────────

async function loadLeaderboard() {
  try {
    const resp = await fetch(API_BASE_URL + "/leaderboard");
    if (!resp.ok) throw new Error("Failed to load leaderboard");
    const data = await resp.json();
    renderLeaderboard(data);
  } catch (err) {
    showError("Could not load leaderboard: " + err.message);
  }
}

function renderLeaderboard(entries) {
  const tbody = document.getElementById("leaderboard-body");
  if (entries.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">No matches yet</td></tr>';
    return;
  }
  tbody.innerHTML = entries
    .map(
      (e, i) => `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(e.team_name)}</td>
      <td>${e.total_wins}</td>
      <td>${e.total_loss}</td>
      <td>${e.total_score}</td>
    </tr>`
    )
    .join("");
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

// ── Register match ───────────────────────────────────────────────────

document.getElementById("match-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const body = {
    team1_name: form.team1_name.value.trim(),
    team2_name: form.team2_name.value.trim(),
    team1_score: parseInt(form.team1_score.value, 10),
    team2_score: parseInt(form.team2_score.value, 10),
  };

  if (!body.team1_name || !body.team2_name) {
    showError("Both team names are required");
    return;
  }
  if (body.team1_score < 0 || body.team2_score < 0 || body.team1_score > 6 || body.team2_score > 6) {
    showError("Scores must be between 0 and 6");
    return;
  }

  try {
    const resp = await fetch(API_BASE_URL + "/matches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    form.reset();
    showSuccess();
    // Switch to scoreboard after a short delay
    setTimeout(() => {
      document.querySelector('[data-tab="scoreboard"]').click();
    }, 1200);
  } catch (err) {
    showError("Failed to submit: " + err.message);
  }
});

// Refresh button
document.getElementById("refresh-btn").addEventListener("click", loadLeaderboard);

// ── Matches ──────────────────────────────────────────────────────────

async function loadMatches() {
  try {
    const resp = await fetch(API_BASE_URL + "/matches");
    if (!resp.ok) throw new Error("Failed to load matches");
    const data = await resp.json();
    renderMatches(data);
  } catch (err) {
    showError("Could not load matches: " + err.message);
  }
}

function renderMatches(matches) {
  const tbody = document.getElementById("matches-body");
  if (matches.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">No matches yet</td></tr>';
    return;
  }
  tbody.innerHTML = matches
    .map(
      (m) => `
    <tr>
      <td>${escapeHtml(m.team1_name)}</td>
      <td class="score-cell">${m.team1_score}</td>
      <td class="score-cell">${m.team2_score}</td>
      <td>${escapeHtml(m.team2_name)}</td>
      <td class="date-cell">${formatDate(m.created_at)}</td>
      <td><button class="btn-delete" onclick="deleteMatch('${m.id}')">✕</button></td>
    </tr>`
    )
    .join("");
}

function formatDate(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString() + " " + d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

async function deleteMatch(matchId) {
  const pin = prompt("Enter admin PIN to delete this match:");
  if (!pin) return;

  try {
    const resp = await fetch(API_BASE_URL + "/matches/" + matchId, {
      method: "DELETE",
      headers: { "X-Admin-Token": pin },
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    loadMatches();
    // Also refresh leaderboard since it depends on matches
    loadLeaderboard();
  } catch (err) {
    showError("Failed to delete match: " + err.message);
  }
}

document.getElementById("refresh-matches-btn").addEventListener("click", loadMatches);

// ── Teams ────────────────────────────────────────────────────────────

async function loadTeams() {
  try {
    const resp = await fetch(API_BASE_URL + "/teams");
    if (!resp.ok) throw new Error("Failed to load teams");
    const data = await resp.json();
    renderTeams(data);
  } catch (err) {
    showError("Could not load teams: " + err.message);
  }
}

function renderTeams(teams) {
  const tbody = document.getElementById("teams-body");
  if (teams.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">No teams registered yet</td></tr>';
    return;
  }
  tbody.innerHTML = teams
    .map(
      (t, i) => `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(t.name)}</td>
      <td>${t.members.map(escapeHtml).join(", ")}</td>
    </tr>`
    )
    .join("");
}

async function populateTeamDropdowns() {
  try {
    const resp = await fetch(API_BASE_URL + "/teams/names");
    if (!resp.ok) throw new Error("Failed to load team names");
    const names = await resp.json();
    const selects = [document.getElementById("team1_name"), document.getElementById("team2_name")];
    selects.forEach((sel) => {
      const current = sel.value;
      sel.innerHTML = '<option value="" disabled selected>Select a team</option>';
      names.forEach((name) => {
        const opt = document.createElement("option");
        opt.value = name;
        opt.textContent = name;
        sel.appendChild(opt);
      });
      // Restore previous selection if still valid
      if (current && names.includes(current)) sel.value = current;
    });
  } catch (err) {
    showError("Could not load team names: " + err.message);
  }
}

document.getElementById("refresh-teams-btn").addEventListener("click", loadTeams);

// Initial load
loadLeaderboard();
populateTeamDropdowns();
