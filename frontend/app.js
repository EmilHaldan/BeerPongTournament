/* ── Beer Pong Tournament – Frontend JS ────────────────────────────── */

// Current matchups cache (populated from heat info)
let currentMatchups = [];

// Timer state
let timerInterval = null;
let buzzerPlayed = false;
let bellPlayed = false;
let countdownSoundsPlayed = new Set(); // track which countdown numbers already played
let lastTimerStartedAt = null; // Track timer state to detect new timer starts
let heatPollInterval = null;
let boardPollInterval = null;

// "My team" highlight — persisted to localStorage, self-heals post-roster-change.
let highlightedTeam = null;
let highlightedPlayer = null;

// Cache of the most recently fetched teams + players. Populated by
// loadTeamsAndPlayers() and consumed by render helpers, the dropdowns, and the
// highlight handlers when they need to resolve a player -> team lookup.
let teamsCache = [];
let playersCache = [];

const HIGHLIGHT_TEAM_KEY = "beerpong.highlightedTeam";
const HIGHLIGHT_PLAYER_KEY = "beerpong.highlightedPlayer";

// Shared AudioContext – unlocked on first user interaction
let sharedAudioCtx = null;
function getAudioCtx() {
  if (!sharedAudioCtx || sharedAudioCtx.state === "closed") {
    sharedAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (sharedAudioCtx.state === "suspended") {
    sharedAudioCtx.resume();
  }
  return sharedAudioCtx;
}

// Unlock audio on first user interaction (tap/click anywhere)
document.addEventListener("click", function unlockAudio() {
  getAudioCtx();
  document.removeEventListener("click", unlockAudio);
}, { once: true });

// Play a countdown beep (constant 900Hz tone)
function playCountdownBeep(number) {
  try {
    const ctx = getAudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 900;
    gain.gain.value = 0;
    osc.connect(gain);
    gain.connect(ctx.destination);
    const t = ctx.currentTime;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(0.7, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.01, t + 0.4);
    osc.start(t);
    osc.stop(t + 0.45);
  } catch (e) {
    console.warn("Countdown beep not supported", e);
  }
}

// Play a boxing ring bell – 4 consecutive "ding" sounds
function playBell() {
  try {
    const ctx = getAudioCtx();
    const dingCount = 4;
    const dingSpacing = 0.3; // seconds between dings

    for (let i = 0; i < dingCount; i++) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = 1200; // high metallic bell tone
      gain.gain.value = 0;
      osc.connect(gain);
      gain.connect(ctx.destination);

      const t = ctx.currentTime + i * dingSpacing;
      // Sharp attack, quick decay like a struck bell
      gain.gain.setValueAtTime(0, t);
      gain.gain.linearRampToValueAtTime(0.9, t + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.01, t + 0.2);
      osc.start(t);
      osc.stop(t + 0.25);
    }
  } catch (e) {
    console.warn("Bell sound not supported", e);
  }
}

// Play a loud buzzer sound using Web Audio API
function playBuzzer() {
  if (buzzerPlayed) return;
  buzzerPlayed = true;
  try {
    const ctx = getAudioCtx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "square";
    osc.frequency.value = 220;
    gain.gain.value = 0.8;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    // Three short buzzes
    setTimeout(() => { gain.gain.value = 0; }, 300);
    setTimeout(() => { gain.gain.value = 0.8; }, 500);
    setTimeout(() => { gain.gain.value = 0; }, 800);
    setTimeout(() => { gain.gain.value = 0.8; }, 1000);
    setTimeout(() => { gain.gain.value = 0; osc.stop(); }, 1300);
  } catch (e) {
    console.warn("Buzzer sound not supported", e);
  }
}

function updateTimerDisplay(timerStartedAt, timerDuration) {
  const timerBlock = document.getElementById("heat-timer-block");
  const timerEl = document.getElementById("heat-timer");
  const timerLabel = timerBlock.querySelector(".heat-number-label");
  if (!timerStartedAt) {
    timerBlock.classList.add("hidden");
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    buzzerPlayed = false;
    bellPlayed = false;
    countdownSoundsPlayed.clear();
    return;
  }

  timerBlock.classList.remove("hidden");
  const startMs = new Date(timerStartedAt).getTime();
  const endMs = startMs + timerDuration * 1000;

  function tick() {
    const now = Date.now();
    const preStartRemaining = startMs - now;

    if (preStartRemaining > 0) {
      // ── Pre-start countdown phase (5, 4, 3, 2, 1) ──
      const countNum = Math.ceil(preStartRemaining / 1200);
      timerLabel.innerHTML = "Get<br>Ready!";
      timerEl.textContent = countNum;
      timerEl.classList.remove("timer-expired");
      timerEl.classList.add("timer-countdown");

      // Play escalating beep for each number (once)
      if (!countdownSoundsPlayed.has(countNum)) {
        countdownSoundsPlayed.add(countNum);
        playCountdownBeep(countNum);
      }
      return;
    }

    // ── Timer just started – play bell once ──
    if (!bellPlayed) {
      bellPlayed = true;
      timerEl.classList.remove("timer-countdown");
      timerLabel.innerHTML = "Time<br>Remaining";
      playBell();
    }

    // ── Normal countdown phase ──
    const remaining = Math.max(0, endMs - now);
    const totalSec = Math.ceil(remaining / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    timerEl.textContent = String(min).padStart(2, "0") + ":" + String(sec).padStart(2, "0");

    if (remaining <= 0) {
      timerEl.textContent = "00:00";
      timerEl.classList.add("timer-expired");
      playBuzzer();
      if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    } else {
      timerEl.classList.remove("timer-expired");
    }
  }

  tick();
  if (timerInterval) clearInterval(timerInterval);
  timerInterval = setInterval(tick, 100);
}

// Tab switching
document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((s) => s.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");

    // Auto-refresh when switching tabs
    if (btn.dataset.tab === "scoreboard") startBoardPolling();
    else stopBoardPolling();
    if (btn.dataset.tab === "matches") loadMatches();
    if (btn.dataset.tab === "teams") loadTeamsAndPlayers();
    if (btn.dataset.tab === "nextheat") startHeatPolling();
    else stopHeatPolling();
    if (btn.dataset.tab === "admin") loadAdminHeatInfo();
    if (btn.dataset.tab === "register") {
      // Refresh the roster cache so dropdowns reflect any CSV uploads, new
      // teams, or deletions that happened since the last visit.
      loadTeamsAndPlayers();
      loadCurrentHeat();
      // Reset cups hit dropdowns to 0
      document.getElementById("team1_score").value = "0";
      document.getElementById("team2_score").value = "0";
    }
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
    tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">No matches yet</td></tr>';
    return;
  }
  // Sort by total score descending
  entries.sort((a, b) => b.total_score - a.total_score);
  const medals = ["\u{1F947}", "\u{1F948}", "\u{1F949}"]; // gold, silver, bronze
  tbody.innerHTML = entries
    .map(
      (e, i) => `
    <tr>
      <td>${i < 3 ? medals[i] : i + 1}</td>
      <td>${escapeHtml(e.team_name)}</td>
      <td>${e.total_score}</td>
      <td>${e.total_wins}</td>
      <td>${e.total_loss}</td>
      <td>${e.total_matches}</td>
    </tr>`
    )
    .join("");
  applyTeamHighlight();
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

// ── Score Animation ──────────────────────────────────────────────────

async function showScoreAnimation(t1Name, t1Cups, t2Name, t2Cups) {
  const overlay = document.getElementById("score-animation-overlay");
  const delay = (ms) => new Promise(r => setTimeout(r, ms));

  let t1Adj = 0, t2Adj = 0;
  if (t1Cups > t2Cups) { t1Adj = 1; t2Adj = -1; }
  else if (t2Cups > t1Cups) { t2Adj = 1; t1Adj = -1; }

  const t1MatchScore = t1Cups + t1Adj;
  const t2MatchScore = t2Cups + t2Adj;

  // Fetch current leaderboard to get total scores (already includes this match)
  let t1Total = 0, t2Total = 0;
  try {
    const resp = await fetch(API_BASE_URL + "/leaderboard");
    if (resp.ok) {
      const board = await resp.json();
      for (const e of board) {
        if (e.team_name === t1Name) t1Total = e.total_score;
        if (e.team_name === t2Name) t2Total = e.total_score;
      }
    }
  } catch (_) { /* ignore */ }

  const t1PrevTotal = t1Total - t1MatchScore;
  const t2PrevTotal = t2Total - t2MatchScore;

  function adjLabel(adj) {
    if (adj > 0) return "+1";
    if (adj < 0) return "-1";
    return "\u00B10";
  }

  // ── Reset everything to clean state ──
  const animClasses = [
    "phase-in", "slide-up", "merge-up", "merge-down",
    "bounce", "fade-out", "slam-in", "win", "loss", "tie"
  ];
  overlay.querySelectorAll("*").forEach(el => {
    animClasses.forEach(c => el.classList.remove(c));
    el.style.color = "";
  });

  // Set content
  const el = (id) => document.getElementById(id);
  el("anim-team1-name").textContent = t1Name;
  el("anim-team1-name").className = "score-anim-name";
  el("anim-team1-cups").textContent = t1Cups;
  el("anim-team1-cups").className = "score-anim-cups";
  el("anim-team1-cups-label").textContent = "cups hit";
  el("anim-team1-cups-label").className = "score-anim-cups-label";
  el("anim-team1-adj").textContent = adjLabel(t1Adj);
  el("anim-team1-adj").className = "score-anim-adj" + (t1Adj > 0 ? " win" : t1Adj < 0 ? " loss" : " tie");
  el("anim-team1-total").textContent = t1PrevTotal;
  el("anim-team1-total").className = "score-anim-total";
  el("anim-team1-total-label").textContent = "total score";
  el("anim-team1-total-label").className = "score-anim-total-label";

  el("anim-team2-name").textContent = t2Name;
  el("anim-team2-name").className = "score-anim-name";
  el("anim-team2-cups").textContent = t2Cups;
  el("anim-team2-cups").className = "score-anim-cups";
  el("anim-team2-cups-label").textContent = "cups hit";
  el("anim-team2-cups-label").className = "score-anim-cups-label";
  el("anim-team2-adj").textContent = adjLabel(t2Adj);
  el("anim-team2-adj").className = "score-anim-adj" + (t2Adj > 0 ? " win" : t2Adj < 0 ? " loss" : " tie");
  el("anim-team2-total").textContent = t2PrevTotal;
  el("anim-team2-total").className = "score-anim-total";
  el("anim-team2-total-label").textContent = "total score";
  el("anim-team2-total-label").className = "score-anim-total-label";

  overlay.querySelector(".score-anim-vs").className = "score-anim-vs";

  // Show overlay and force reflow to reset CSS animations
  overlay.classList.remove("hidden", "fade-out");
  void overlay.offsetHeight;

  // Helper shorthand
  const $ = (sel) => overlay.querySelector(sel);
  const $$ = (sel) => overlay.querySelectorAll(sel);

  // ── Phase 1: Names + VS pop in ──
  $$(".score-anim-name").forEach(e => e.classList.add("phase-in"));
  $(".score-anim-vs").classList.add("phase-in");
  await delay(400);

  // ── Phase 2: Cup scores pop in ──
  $$(".score-anim-cups").forEach(e => e.classList.add("phase-in"));
  $$(".score-anim-cups-label").forEach(e => e.classList.add("phase-in"));
  await delay(1000);

  // ── Phase 3: +1/-1 slide up from bottom ──
  $$(".score-anim-adj").forEach(e => e.classList.add("slide-up"));
  await delay(1200);

  // ── Phase 4: +1/-1 merge UP into cups, cups bounce + update ──
  $$(".score-anim-adj").forEach(e => {
    e.classList.remove("slide-up");
    void e.offsetHeight;
    e.classList.add("merge-up");
  });
  await delay(250);
  const cups1 = el("anim-team1-cups");
  const cups2 = el("anim-team2-cups");
  cups1.textContent = t1MatchScore;
  cups2.textContent = t2MatchScore;
  cups1.className = "score-anim-cups bounce";
  cups2.className = "score-anim-cups bounce";
  $$(".score-anim-cups-label").forEach(e => e.textContent = "match score");
  await delay(1200);

  // ── Phase 5: Previous total slides up from bottom ──
  $$(".score-anim-total").forEach(e => e.classList.add("slide-up"));
  $$(".score-anim-total-label").forEach(e => e.classList.add("slide-up"));
  await delay(1200);

  // ── Phase 6: Cups merge DOWN into total, total bounces + updates ──
  cups1.className = "score-anim-cups merge-down";
  cups2.className = "score-anim-cups merge-down";
  $$(".score-anim-cups-label").forEach(e => {
    e.className = "score-anim-cups-label fade-out";
  });
  await delay(300);
  const total1 = el("anim-team1-total");
  const total2 = el("anim-team2-total");
  total1.textContent = t1Total;
  total2.textContent = t2Total;
  total1.className = "score-anim-total bounce";
  total2.className = "score-anim-total bounce";
  total1.style.color = "var(--text)";
  total2.style.color = "var(--text)";
  await delay(2000);

  // ── Fade out ──
  overlay.classList.add("fade-out");
  await delay(600);
  overlay.classList.add("hidden");
  overlay.classList.remove("fade-out");
  document.querySelector('[data-tab="scoreboard"]').click();
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
    heat: parseInt(form.heat.value, 10) || 1,
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
    showScoreAnimation(body.team1_name, body.team1_score, body.team2_name, body.team2_score);
  } catch (err) {
    showError("Failed to submit: " + err.message);
  }
});


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
    tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">No matches yet</td></tr>';
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
      <td class="score-cell">${m.heat}</td>
      <td class="date-cell">${formatDate(m.created_at)}</td>
      <td><button class="btn-delete" onclick="deleteMatch('${m.id}')">✕</button></td>
    </tr>`
    )
    .join("");
  applyTeamHighlight();
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


// ── Teams + Players ──────────────────────────────────────────────────

async function loadTeamsAndPlayers() {
  try {
    const [teamsResp, playersResp] = await Promise.all([
      fetch(API_BASE_URL + "/teams"),
      fetch(API_BASE_URL + "/players"),
    ]);
    if (!teamsResp.ok) throw new Error("Failed to load teams");
    if (!playersResp.ok) throw new Error("Failed to load players");
    const [teams, players] = await Promise.all([teamsResp.json(), playersResp.json()]);
    teamsCache = teams;
    playersCache = players;
    renderTeams(teams, players);
    renderRegisteredPlayers(players, teams);
    populateTeamDropdowns();
  } catch (err) {
    showError("Could not load roster: " + err.message);
  }
}

function _playerNameById(players, playerId) {
  const hit = players.find(p => p.id === playerId);
  return hit ? hit.name : "";
}

function _teamNameByPlayerId(teams, playerTeamId) {
  if (!playerTeamId) return "";
  const hit = teams.find(t => t.id === playerTeamId);
  return hit ? hit.name : "";
}

function renderTeams(teams, players) {
  const tbody = document.getElementById("teams-body");
  // Public Teams tab hides 0-member teams entirely — admin-only per spec.
  const visible = (teams || []).filter(t => (t.member_ids || []).length > 0);
  if (visible.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">No teams registered yet</td></tr>';
    return;
  }
  tbody.innerHTML = visible
    .map(
      (t, i) => {
        const memberNames = (t.member_ids || [])
          .map(pid => _playerNameById(players || [], pid))
          .filter(n => n.length > 0);
        const memberSpans = memberNames
          .map(name => `<span class="team-member-name" data-player="${escapeHtml(name)}">${escapeHtml(name)}</span>`)
          .join(", ");
        // The team checkbox stays checked whenever the active team matches —
        // including when a player on that team is the primary selection, since
        // player selection auto-checks the parent team.
        const teamChecked = highlightedTeam === t.name ? "checked" : "";
        return `
    <tr>
      <td>${i + 1}</td>
      <td class="team-name-cell" data-team="${escapeHtml(t.name)}">${escapeHtml(t.name)}</td>
      <td>${memberSpans}</td>
      <td><input type="checkbox" class="team-check" data-team="${escapeHtml(t.name)}" ${teamChecked} /></td>
    </tr>`;
      }
    )
    .join("");
  applyTeamHighlight();
}

function renderRegisteredPlayers(players, teams) {
  const tbody = document.getElementById("players-body");
  const safePlayers = (players || []).slice();
  if (safePlayers.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">No players registered yet</td></tr>';
    return;
  }
  // Sort by name using the default locale — handles Danish Æ/Ø/Å correctly.
  safePlayers.sort((a, b) => a.name.localeCompare(b.name));
  tbody.innerHTML = safePlayers
    .map(
      (p, i) => {
        const teamName = _teamNameByPlayerId(teams || [], p.team_id);
        const unassigned = !p.team_id;
        const rowCls = unassigned ? ' class="player-unassigned"' : '';
        const checked = highlightedPlayer === p.name ? "checked" : "";
        return `
    <tr${rowCls}>
      <td>${i + 1}</td>
      <td class="player-name-cell" data-player="${escapeHtml(p.name)}">${escapeHtml(p.name)}</td>
      <td><input type="checkbox" class="player-check" data-player="${escapeHtml(p.name)}" data-team="${escapeHtml(teamName)}" ${checked} /></td>
    </tr>`;
      }
    )
    .join("");
  applyTeamHighlight();
}

function populateTeamDropdowns() {
  // Filter 0-member teams out client-side since /teams/names does not.
  const names = (teamsCache || [])
    .filter(t => (t.member_ids || []).length > 0)
    .map(t => t.name)
    .sort((a, b) => a.localeCompare(b));
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
  // Auto-select highlighted team as Team 1 and trigger opponent auto-fill
  const team1Sel = document.getElementById("team1_name");
  if (highlightedTeam && names.includes(highlightedTeam)) {
    team1Sel.value = highlightedTeam;
    team1Sel.dispatchEvent(new Event("change"));
  }
}


// Auto-select opponent when a team is selected in Register Score
document.getElementById("team1_name").addEventListener("change", () => {
  const selected = document.getElementById("team1_name").value;
  if (!selected || currentMatchups.length === 0) return;
  for (const m of currentMatchups) {
    if (m.team1_name === selected) {
      document.getElementById("team2_name").value = m.team2_name;
      return;
    }
    if (m.team2_name === selected) {
      document.getElementById("team2_name").value = m.team1_name;
      return;
    }
  }
});

document.getElementById("team2_name").addEventListener("change", () => {
  const selected = document.getElementById("team2_name").value;
  if (!selected || currentMatchups.length === 0) return;
  for (const m of currentMatchups) {
    if (m.team1_name === selected) {
      document.getElementById("team1_name").value = m.team2_name;
      return;
    }
    if (m.team2_name === selected) {
      document.getElementById("team1_name").value = m.team1_name;
      return;
    }
  }
});


// ── Heat ─────────────────────────────────────────────────────────────────

async function loadHeatInfo() {
  try {
    const resp = await fetch(API_BASE_URL + "/heat");
    if (!resp.ok) throw new Error("Failed to load heat info");
    const data = await resp.json();

    // Detect when a timer just started (track for state change)
    lastTimerStartedAt = data.timer_started_at || null;

    renderHeatInfo(data);
  } catch (err) {
    showError("Could not load heat info: " + err.message);
  }
}

function startHeatPolling() {
  loadHeatInfo();
  stopHeatPolling();
  heatPollInterval = setInterval(loadHeatInfo, 1000);
}

function stopHeatPolling() {
  if (heatPollInterval) { clearInterval(heatPollInterval); heatPollInterval = null; }
}

function startBoardPolling() {
  loadLeaderboard();
  stopBoardPolling();
  boardPollInterval = setInterval(loadLeaderboard, 1000);
}

function stopBoardPolling() {
  if (boardPollInterval) { clearInterval(boardPollInterval); boardPollInterval = null; }
}

function renderHeatInfo(heatInfo) {
  // Cache matchups for auto-select in Register Score
  currentMatchups = heatInfo.matchups || [];

  document.getElementById("heat-number").textContent = heatInfo.current_heat;

  // Update timer display
  updateTimerDisplay(heatInfo.timer_started_at, heatInfo.timer_duration || 600);

  const container = document.getElementById("heat-matchups");

  if (!heatInfo.matchups || heatInfo.matchups.length === 0) {
    container.innerHTML = '<p class="empty-msg">No matchups available – register more teams</p>';
    return;
  }

  container.innerHTML = heatInfo.matchups
    .map(
      (m, idx) => {
        // Underdog (team2, lower pts) goes on the left as Red (starts first)
        // Favorite (team1, higher pts) goes on the right as Blue
        const redName = m.team2_name;
        const blueName = m.team1_name;
        const redScore = m.team2_score;
        const blueScore = m.team1_score;

        // Display updated points if match is recorded (original + cups + win/loss bonus)
        let redPts = m.team2_points;
        let bluePts = m.team1_points;
        if (m.recorded && redScore != null && blueScore != null) {
          const redBonus = redScore > blueScore ? 1 : redScore < blueScore ? -1 : 0;
          const blueBonus = blueScore > redScore ? 1 : blueScore < redScore ? -1 : 0;
          redPts += redScore + redBonus;
          bluePts += blueScore + blueBonus;
        }

        const redWinner = m.winner === redName;
        const blueWinner = m.winner === blueName;
        const winnerClass = redWinner ? 'winner-left' : blueWinner ? 'winner-right' : '';
        const recordedClass = m.recorded ? 'matchup-recorded' : 'matchup-pending';
        const scoreText = m.recorded
          ? `<span class="matchup-score">${redScore} \u2013 ${blueScore}</span>`
          : '<span class="matchup-score pending">Not recorded</span>';
        const tableNumber = idx + 1;

        return `
    <div class="matchup-card ${recordedClass} ${winnerClass}">
      <div class="matchup-team red-side">
        <div class="matchup-name-row"><span class="matchup-color red">\u{1F534}</span><span class="matchup-name">${escapeHtml(redName)}</span></div>
        <span class="matchup-pts">${redPts} pts</span>
      </div>
      <div class="matchup-center">
        <div class="matchup-table">Table ${tableNumber}</div>
        <div class="matchup-vs">VS</div>
        ${scoreText}
      </div>
      <div class="matchup-team blue-side">
        <div class="matchup-name-row"><span class="matchup-name">${escapeHtml(blueName)}</span><span class="matchup-color blue">\u{1F535}</span></div>
        <span class="matchup-pts">${bluePts} pts</span>
      </div>
    </div>`;
      }
    )
    .join("");

  // Summary line
  const total = heatInfo.teams_recorded.length + heatInfo.teams_not_recorded.length;
  const recorded = heatInfo.teams_recorded.length;
  container.innerHTML += `
    <div class="heat-summary">
      <span>${recorded} / ${total} teams recorded</span>
    </div>`;

  // Sitting-out section
  const sittingSection = document.getElementById("heat-sitting-out");
  const sittingList = document.getElementById("heat-sitting-out-list");
  const sitting = heatInfo.teams_sitting_out || [];
  if (sittingSection && sittingList) {
    if (sitting.length === 0) {
      sittingSection.classList.add("hidden");
      sittingList.innerHTML = "";
    } else {
      sittingSection.classList.remove("hidden");
      sittingList.innerHTML = sitting
        .map((name) => `<li>${escapeHtml(name)}</li>`)
        .join("");
    }
  }

  applyTeamHighlight();
}

async function loadCurrentHeat() {
  try {
    const resp = await fetch(API_BASE_URL + "/heat");
    if (!resp.ok) throw new Error("Failed to load heat");
    const data = await resp.json();
    document.getElementById("heat").value = data.current_heat;
  } catch (err) {
    // Silently fall back to 1
    document.getElementById("heat").value = 1;
  }
}

document.getElementById("start-next-heat-btn").addEventListener("click", async () => {
  const lastHeatCheckbox = document.getElementById("last-heat-checkbox");
  const lastHeat = !!(lastHeatCheckbox && lastHeatCheckbox.checked);
  const promptMsg = lastHeat
    ? "Setup the next (LAST) heat – teams with the fewest games get priority. Continue?"
    : "This will setup the next heat (advance heat number and generate new matchups). Continue?";
  if (!confirm(promptMsg)) return;

  try {
    const resp = await fetch(API_BASE_URL + "/heat/start-next", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ last_heat: lastHeat }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    const data = await resp.json();
    renderHeatInfo(data);
    updateAdminHeat(data.current_heat);
    // Reset the checkbox so it does not carry over to the next invocation.
    if (lastHeatCheckbox) lastHeatCheckbox.checked = false;
  } catch (err) {
    showError("Could not setup next heat: " + err.message);
  }
});

document.getElementById("start-heat-timer-btn").addEventListener("click", async () => {
  if (!confirm("Start the heat timer? The countdown will be visible to all players.")) return;

  // Unlock audio context within user gesture
  getAudioCtx();

  try {
    const resp = await fetch(API_BASE_URL + "/heat/start-timer", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    const data = await resp.json();
    renderHeatInfo(data);
    updateAdminHeat(data.current_heat);
  } catch (err) {
    showError("Could not start heat timer: " + err.message);
  }
});

document.getElementById("set-heat-btn").addEventListener("click", async () => {
  const heatStr = prompt("Enter the heat number to set:");
  if (!heatStr) return;
  const heatNum = parseInt(heatStr, 10);
  if (isNaN(heatNum) || heatNum < 1) {
    showError("Heat must be a positive number");
    return;
  }

  try {
    const resp = await fetch(API_BASE_URL + "/heat/set", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ heat: heatNum }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    const data = await resp.json();
    renderHeatInfo(data);
    updateAdminHeat(data.current_heat);
  } catch (err) {
    showError("Could not set heat: " + err.message);
  }
});


// ── Admin ─────────────────────────────────────────────────────────────

let adminToken = null;

function updateAdminHeat(heatNum) {
  document.getElementById("admin-heat-number").textContent = heatNum;
}

async function loadAdminHeatInfo() {
  try {
    const resp = await fetch(API_BASE_URL + "/heat");
    if (!resp.ok) return;
    const data = await resp.json();
    updateAdminHeat(data.current_heat);
    const durationInput = document.getElementById("timer-duration");
    if (durationInput) {
      const minutes = Math.max(1, Math.round((data.timer_duration || 600) / 60));
      durationInput.value = String(minutes);
    }
    const tablesInput = document.getElementById("tables-count");
    if (tablesInput) {
      tablesInput.value = String(data.tables || 8);
    }
  } catch (err) {
    // ignore
  }
}

document.getElementById("admin-login-btn").addEventListener("click", async () => {
  const pin = document.getElementById("admin-pin").value.trim();
  if (!pin) return;

  // Validate the PIN by making a lightweight admin call
  try {
    const resp = await fetch(API_BASE_URL + "/admin/verify", {
      method: "POST",
      headers: { "X-Admin-Token": pin },
    });
    if (!resp.ok) {
      document.getElementById("admin-error").classList.remove("hidden");
      setTimeout(() => document.getElementById("admin-error").classList.add("hidden"), 3000);
      return;
    }
    adminToken = pin;
    document.getElementById("admin-login").classList.add("hidden");
    document.getElementById("admin-panel").classList.remove("hidden");
    loadAdminHeatInfo();
    // Prime the public cache first so the admin render helpers can resolve
    // player-id → name and player team_id → team-name without racing.
    await loadTeamsAndPlayers();
    loadAdminTeams();
    loadAdminPlayers();
  } catch (err) {
    showError("Could not verify PIN: " + err.message);
  }
});

// Allow pressing Enter in the PIN field
document.getElementById("admin-pin").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    document.getElementById("admin-login-btn").click();
  }
});

// ── Admin: Create Team ────────────────────────────────────────────────

document.getElementById("add-team-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("new-team-name").value.trim();

  if (!name) {
    showError("Team name is required");
    return;
  }

  try {
    const resp = await fetch(API_BASE_URL + "/teams", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ name, member_ids: [] }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    document.getElementById("add-team-form").reset();
    const msg = document.getElementById("add-team-success");
    msg.classList.remove("hidden");
    setTimeout(() => msg.classList.add("hidden"), 3000);
    // Refresh the public cache so name/id lookups stay in sync, then
    // re-render the admin table.
    await loadTeamsAndPlayers();
    loadAdminTeams();
  } catch (err) {
    showError("Failed to create team: " + err.message);
  }
});

// ── Admin: Manage Teams ───────────────────────────────────────────────

async function loadAdminTeams() {
  try {
    const resp = await fetch(API_BASE_URL + "/teams");
    if (!resp.ok) throw new Error("Failed to load teams");
    const data = await resp.json();
    renderAdminTeams(data);
  } catch (err) {
    showError("Could not load teams: " + err.message);
  }
}

function renderAdminTeams(teams) {
  const tbody = document.getElementById("admin-teams-body");
  if (teams.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">No teams yet</td></tr>';
    return;
  }
  tbody.innerHTML = teams
    .map(
      (t, i) => {
        const memberIds = t.member_ids || [];
        let membersCell;
        if (memberIds.length === 0) {
          membersCell = '<span class="muted">&mdash; (no members)</span>';
        } else {
          const names = memberIds
            .map((pid) => _playerNameById(playersCache || [], pid))
            .filter((n) => n.length > 0)
            .map(escapeHtml);
          membersCell = names.join(", ");
        }
        return `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(t.name)}</td>
      <td>${membersCell}</td>
      <td><button class="btn-delete" onclick="deleteTeam('${t.id}')">✕</button></td>
    </tr>`;
      }
    )
    .join("");
}

async function deleteTeam(teamId) {
  if (!confirm("Are you sure you want to remove this team?")) return;

  try {
    const resp = await fetch(API_BASE_URL + "/teams/" + teamId, {
      method: "DELETE",
      headers: { "X-Admin-Token": adminToken },
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    // Detach cascades to players — refresh every roster-backed view.
    await loadTeamsAndPlayers();
    loadAdminTeams();
    loadAdminPlayers();
  } catch (err) {
    showError("Failed to delete team: " + err.message);
  }
}

// ── Admin: Add Player ─────────────────────────────────────────────────

document.getElementById("add-player-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("new-player-name").value.trim();

  if (!name) {
    showError("Player name is required");
    return;
  }

  try {
    const resp = await fetch(API_BASE_URL + "/players", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ name }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    document.getElementById("add-player-form").reset();
    const msg = document.getElementById("add-player-success");
    msg.classList.remove("hidden");
    setTimeout(() => msg.classList.add("hidden"), 3000);
    loadAdminPlayers();
    // Refresh the public Teams tab (which now hosts the Registered Players list).
    if (document.getElementById("tab-teams").classList.contains("active")) {
      loadTeamsAndPlayers();
    }
  } catch (err) {
    showError("Failed to add player: " + err.message);
  }
});

// ── Admin: Manage Players ─────────────────────────────────────────────

async function loadAdminPlayers() {
  try {
    const resp = await fetch(API_BASE_URL + "/players");
    if (!resp.ok) throw new Error("Failed to load players");
    const data = await resp.json();
    renderAdminPlayers(data);
  } catch (err) {
    showError("Could not load players: " + err.message);
  }
}

function renderAdminPlayers(players) {
  const tbody = document.getElementById("admin-players-body");
  if (players.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">No players yet</td></tr>';
    return;
  }
  tbody.innerHTML = players
    .map(
      (p, i) => {
        const teamName = _teamNameByPlayerId(teamsCache || [], p.team_id);
        const teamCell = p.team_id
          ? escapeHtml(teamName || "(unknown)")
          : '<span class="muted">Unassigned</span>';
        const currentTeamAttr = p.team_id ? escapeHtml(p.team_id) : "";
        return `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(p.name)}</td>
      <td>${teamCell}</td>
      <td class="admin-player-actions">
        <button class="btn-assign" data-player-id="${escapeHtml(p.id)}" data-player-name="${escapeHtml(p.name)}" data-current-team-id="${currentTeamAttr}">Assign Team</button>
        <button class="btn-delete" onclick="deletePlayer('${p.id}')">&#10005;</button>
      </td>
    </tr>`;
      }
    )
    .join("");
}

async function deletePlayer(playerId) {
  if (!confirm("Are you sure you want to remove this player?")) return;

  try {
    const resp = await fetch(API_BASE_URL + "/players/" + playerId, {
      method: "DELETE",
      headers: { "X-Admin-Token": adminToken },
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    // Deleting a player also strips them from their team's member_ids, so
    // the admin Teams view needs the refresh too.
    await loadTeamsAndPlayers();
    loadAdminPlayers();
    loadAdminTeams();
  } catch (err) {
    showError("Failed to delete player: " + err.message);
  }
}

// ── Admin: Game Settings (timer duration + tables) ─────────────────────

function parsePositiveInt(raw) {
  if (raw === null || raw === undefined) return null;
  const trimmed = String(raw).trim();
  if (trimmed === "") return null;
  if (!/^-?\d+$/.test(trimmed)) return null;
  const n = parseInt(trimmed, 10);
  if (!Number.isFinite(n) || n < 1) return null;
  return n;
}

function setGameSettingsFeedback(msg, kind) {
  const el = document.getElementById("game-settings-feedback");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden", "error", "success");
  el.classList.add(kind);
  if (kind === "success") {
    setTimeout(() => { el.classList.add("hidden"); }, 3000);
  }
}

function clearGameSettingsFeedback() {
  const el = document.getElementById("game-settings-feedback");
  if (el) el.classList.add("hidden");
}

document.getElementById("save-game-settings-btn").addEventListener("click", async () => {
  const btn = document.getElementById("save-game-settings-btn");
  const minutesRaw = document.getElementById("timer-duration").value;
  const tablesRaw = document.getElementById("tables-count").value;

  const minutes = parsePositiveInt(minutesRaw);
  const tables = parsePositiveInt(tablesRaw);

  clearGameSettingsFeedback();

  if (minutes === null) {
    setGameSettingsFeedback("Match duration must be a whole number of minutes (1 or more)", "error");
    return;
  }
  if (tables === null) {
    setGameSettingsFeedback("Tables must be a whole number (1 or more)", "error");
    return;
  }

  const seconds = minutes * 60;

  try {
    const timerResp = await fetch(API_BASE_URL + "/heat/timer-duration", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ seconds }),
    });
    if (!timerResp.ok) {
      const detail = await timerResp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + timerResp.status);
    }

    const tablesResp = await fetch(API_BASE_URL + "/heat/tables", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ count: tables }),
    });
    if (!tablesResp.ok) {
      const detail = await tablesResp.json().catch(() => ({}));
      throw new Error(
        "Timer saved, but tables update failed: " +
          (detail.detail || "Server error " + tablesResp.status)
      );
    }

    btn.textContent = "Saved!";
    setGameSettingsFeedback("Game settings saved.", "success");
    setTimeout(() => { btn.textContent = "Save Game Settings"; }, 2000);
  } catch (err) {
    setGameSettingsFeedback(err.message, "error");
  }
});

// ── Team / Player Highlight ───────────────────────────────────────────

function _persistHighlightState() {
  try {
    if (highlightedTeam) {
      localStorage.setItem(HIGHLIGHT_TEAM_KEY, highlightedTeam);
    } else {
      localStorage.removeItem(HIGHLIGHT_TEAM_KEY);
    }
    if (highlightedPlayer) {
      localStorage.setItem(HIGHLIGHT_PLAYER_KEY, highlightedPlayer);
    } else {
      localStorage.removeItem(HIGHLIGHT_PLAYER_KEY);
    }
  } catch (_) {
    // localStorage may be unavailable in private mode — silent fallback.
  }
}

function _clearAllHighlightCheckboxes() {
  document.querySelectorAll(".team-check, .player-check").forEach(cb => {
    cb.checked = false;
  });
}

function _syncHighlightCheckboxes() {
  document.querySelectorAll(".team-check").forEach(cb => {
    cb.checked = !!(highlightedTeam && cb.dataset.team === highlightedTeam);
  });
  document.querySelectorAll(".player-check").forEach(cb => {
    cb.checked = !!(highlightedPlayer && cb.dataset.player === highlightedPlayer);
  });
}

function applyTeamHighlight() {
  const cls = "team-highlight-text";

  // 1. Clear every existing highlight class before re-applying.
  document.querySelectorAll("." + cls).forEach(el => el.classList.remove(cls));

  // 2. Team-name glow. Matches team-name cells (team row, scoreboard row,
  //    matches history, matchup cards, register-score <select>).
  if (highlightedTeam) {
    // Teams tab team-name cell
    document.querySelectorAll("#teams-body .team-name-cell").forEach(el => {
      if (el.dataset.team === highlightedTeam) el.classList.add(cls);
    });

    // Leaderboard — team name is in col 2
    document.querySelectorAll("#leaderboard-body tr").forEach(tr => {
      const nameCell = tr.querySelector("td:nth-child(2)");
      if (nameCell && nameCell.textContent === highlightedTeam) nameCell.classList.add(cls);
    });

    // Match history — team1 (col 1) and team2 (col 4)
    document.querySelectorAll("#matches-body tr").forEach(tr => {
      const t1 = tr.querySelector("td:nth-child(1)");
      const t2 = tr.querySelector("td:nth-child(4)");
      if (t1 && t1.textContent === highlightedTeam) t1.classList.add(cls);
      if (t2 && t2.textContent === highlightedTeam) t2.classList.add(cls);
    });

    // Next-heat matchup cards
    document.querySelectorAll(".matchup-name").forEach(el => {
      if (el.textContent === highlightedTeam) el.classList.add(cls);
    });

    // Register Score dropdowns — glow the select when the active value matches
    ["team1_name", "team2_name"].forEach(id => {
      const sel = document.getElementById(id);
      if (sel && sel.value === highlightedTeam) sel.classList.add(cls);
    });
  }

  // 3. Player-name glow. Only individual member cells (never a whole team row)
  //    and the Registered Players table row itself.
  if (highlightedPlayer) {
    document.querySelectorAll("#teams-body .team-member-name").forEach(el => {
      if (el.dataset.player === highlightedPlayer) el.classList.add(cls);
    });
    document.querySelectorAll("#players-body .player-name-cell").forEach(el => {
      if (el.dataset.player === highlightedPlayer) el.classList.add(cls);
    });
  }
}

function _selectTeam(teamName) {
  highlightedTeam = teamName || null;
  highlightedPlayer = null;
  _persistHighlightState();
  _syncHighlightCheckboxes();
  applyTeamHighlight();
}

function _selectPlayer(playerName, teamName) {
  highlightedPlayer = playerName || null;
  highlightedTeam = teamName || null;
  _persistHighlightState();
  _syncHighlightCheckboxes();
  applyTeamHighlight();
}

function _clearHighlights() {
  highlightedTeam = null;
  highlightedPlayer = null;
  _persistHighlightState();
  _clearAllHighlightCheckboxes();
  applyTeamHighlight();
}

// Event delegation for team + player checkboxes — mutual exclusion across
// both sets, with the player→team auto-resolve rule.
document.getElementById("teams-body").addEventListener("change", (e) => {
  const target = e.target;
  if (target.classList.contains("team-check")) {
    if (target.checked) {
      _selectTeam(target.dataset.team);
    } else {
      // Any uncheck clears both highlights (simple model per spec).
      _clearHighlights();
    }
  }
});

document.getElementById("players-body").addEventListener("change", (e) => {
  const target = e.target;
  if (!target.classList.contains("player-check")) return;
  if (target.checked) {
    const playerName = target.dataset.player;
    // Prefer the fresh cache over the dataset, which could be stale if the
    // player was reassigned between renders. Fall back to the dataset.
    const fromCache = (playersCache || []).find(p => p.name === playerName);
    let teamName = target.dataset.team || "";
    if (fromCache) {
      teamName = _teamNameByPlayerId(teamsCache || [], fromCache.team_id);
    }
    _selectPlayer(playerName, teamName);
  } else {
    _clearHighlights();
  }
});

function _restoreHighlightFromStorage() {
  let cachedTeam = null;
  let cachedPlayer = null;
  try {
    cachedTeam = localStorage.getItem(HIGHLIGHT_TEAM_KEY);
    cachedPlayer = localStorage.getItem(HIGHLIGHT_PLAYER_KEY);
  } catch (_) {
    return;
  }
  if (!cachedTeam && !cachedPlayer) return;

  const teamNames = (teamsCache || []).map(t => t.name);
  const playerNames = (playersCache || []).map(p => p.name);

  // Self-heal: if either cached value is missing from the current roster,
  // wipe both and exit (post-CSV-upload recovery path).
  const teamStillThere = !cachedTeam || teamNames.includes(cachedTeam);
  const playerStillThere = !cachedPlayer || playerNames.includes(cachedPlayer);
  if (!teamStillThere || !playerStillThere) {
    _clearHighlights();
    return;
  }

  if (cachedPlayer) {
    const playerRecord = (playersCache || []).find(p => p.name === cachedPlayer);
    const resolvedTeam = playerRecord
      ? _teamNameByPlayerId(teamsCache || [], playerRecord.team_id)
      : "";
    _selectPlayer(cachedPlayer, resolvedTeam);
  } else if (cachedTeam) {
    _selectTeam(cachedTeam);
  }
}

// ── Admin: Assign Team modal ──────────────────────────────────────────

// Captures the player currently being assigned. Null when the modal is idle.
let assignModalPlayerId = null;

function _setAssignModalFeedback(msg, kind) {
  const el = document.getElementById("assign-modal-feedback");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden", "error", "success");
  el.classList.add(kind);
}

function _clearAssignModalFeedback() {
  const el = document.getElementById("assign-modal-feedback");
  if (el) {
    el.classList.add("hidden");
    el.textContent = "";
  }
}

function _updateAssignModalTeamInfo() {
  const sel = document.getElementById("assign-team-select");
  const info = document.getElementById("assign-modal-team-info");
  if (!sel || !info) return;
  const teamId = sel.value;
  if (!teamId) {
    info.textContent = "";
    return;
  }
  const team = (teamsCache || []).find((t) => t.id === teamId);
  if (!team) {
    info.textContent = "";
    return;
  }
  const count = (team.member_ids || []).length;
  const noun = count === 1 ? "member" : "members";
  info.textContent = `${team.name} currently has ${count} ${noun}`;
}

function openAssignTeamModal(playerId, playerName, currentTeamId) {
  assignModalPlayerId = playerId;

  const nameEl = document.getElementById("assign-modal-player-name");
  if (nameEl) nameEl.textContent = playerName || "Player";

  const sel = document.getElementById("assign-team-select");
  if (sel) {
    const teams = (teamsCache || []).slice().sort((a, b) => a.name.localeCompare(b.name));
    const opts = ['<option value="">Unassigned</option>'].concat(
      teams.map((t) => `<option value="${escapeHtml(t.id)}">${escapeHtml(t.name)}</option>`)
    );
    sel.innerHTML = opts.join("");
    sel.value = currentTeamId || "";
  }

  _clearAssignModalFeedback();
  _updateAssignModalTeamInfo();

  const modal = document.getElementById("assign-team-modal");
  if (modal) modal.classList.remove("hidden");
}

function closeAssignTeamModal() {
  assignModalPlayerId = null;
  const modal = document.getElementById("assign-team-modal");
  if (modal) modal.classList.add("hidden");
  _clearAssignModalFeedback();
}

// Delegated click handler for the per-row "Assign Team" buttons in the
// Manage Players table. Delegation beats re-binding after every render.
document.getElementById("admin-players-body").addEventListener("click", (e) => {
  const btn = e.target.closest(".btn-assign");
  if (!btn) return;
  const playerId = btn.dataset.playerId || "";
  const playerName = btn.dataset.playerName || "";
  const currentTeamId = btn.dataset.currentTeamId || "";
  if (!playerId) return;
  openAssignTeamModal(playerId, playerName, currentTeamId);
});

document.getElementById("assign-team-select").addEventListener("change", _updateAssignModalTeamInfo);

document.getElementById("assign-team-cancel").addEventListener("click", () => {
  closeAssignTeamModal();
});

document.getElementById("assign-team-save").addEventListener("click", async () => {
  if (!assignModalPlayerId) return;
  const sel = document.getElementById("assign-team-select");
  const raw = sel ? sel.value : "";
  const teamId = raw === "" ? null : raw;

  try {
    const resp = await fetch(API_BASE_URL + "/players/" + assignModalPlayerId + "/team", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ team_id: teamId }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      const msg = typeof detail.detail === "string" ? detail.detail : "Server error " + resp.status;
      _setAssignModalFeedback(msg, "error");
      return;
    }
    closeAssignTeamModal();
    await loadTeamsAndPlayers();
    loadAdminTeams();
    loadAdminPlayers();
  } catch (err) {
    _setAssignModalFeedback("Failed to assign team: " + err.message, "error");
  }
});

// ── Admin: Roster CSV upload ──────────────────────────────────────────

// The file reference held between preview and confirm.
let pendingRosterFile = null;

function _setRosterFeedback(msg, kind) {
  const el = document.getElementById("roster-upload-feedback");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden", "error", "success");
  el.classList.add(kind);
}

function _clearRosterFeedback() {
  const el = document.getElementById("roster-upload-feedback");
  if (el) {
    el.classList.add("hidden");
    el.textContent = "";
  }
}

function _renderRosterPreview(summary) {
  const wrapper = document.getElementById("roster-preview");
  const teamsList = document.getElementById("roster-preview-teams");
  const playersList = document.getElementById("roster-preview-players");
  const errorsWrap = document.getElementById("roster-preview-errors");
  if (!wrapper || !teamsList || !playersList || !errorsWrap) return;

  const teams = summary.created_teams || [];
  const players = summary.created_players || [];
  teamsList.innerHTML = teams.length
    ? teams.map((n) => `<li>${escapeHtml(n)}</li>`).join("")
    : '<li class="muted">None</li>';
  playersList.innerHTML = players.length
    ? players.map((n) => `<li>${escapeHtml(n)}</li>`).join("")
    : '<li class="muted">None</li>';

  const errorsUl = errorsWrap.querySelector("ul");
  if (errorsUl) errorsUl.innerHTML = "";
  errorsWrap.classList.add("hidden");

  wrapper.classList.remove("hidden");
}

function _renderRosterErrors(errors) {
  const wrapper = document.getElementById("roster-preview");
  const errorsWrap = document.getElementById("roster-preview-errors");
  const teamsList = document.getElementById("roster-preview-teams");
  const playersList = document.getElementById("roster-preview-players");
  if (!wrapper || !errorsWrap) return;
  if (teamsList) teamsList.innerHTML = '<li class="muted">None</li>';
  if (playersList) playersList.innerHTML = '<li class="muted">None</li>';
  const ul = errorsWrap.querySelector("ul");
  if (ul) {
    ul.innerHTML = (errors || [])
      .map((e) => `<li>Row ${e.row}: ${escapeHtml(e.reason)}</li>`)
      .join("");
  }
  errorsWrap.classList.remove("hidden");
  wrapper.classList.remove("hidden");
}

function _clearRosterPreview() {
  const wrapper = document.getElementById("roster-preview");
  if (wrapper) wrapper.classList.add("hidden");
  const errorsWrap = document.getElementById("roster-preview-errors");
  if (errorsWrap) errorsWrap.classList.add("hidden");
}

function _setConfirmEnabled(enabled) {
  const btn = document.getElementById("roster-confirm-btn");
  if (btn) btn.disabled = !enabled;
}

document.getElementById("roster-preview-btn").addEventListener("click", async () => {
  const input = document.getElementById("roster-csv-file");
  const file = input && input.files && input.files[0] ? input.files[0] : null;

  if (!file) {
    _setRosterFeedback("Select a CSV file first.", "error");
    _setConfirmEnabled(false);
    return;
  }

  _clearRosterFeedback();
  _clearRosterPreview();
  _setConfirmEnabled(false);

  const fd = new FormData();
  fd.append("file", file);

  try {
    const resp = await fetch(API_BASE_URL + "/admin/teams/upload-csv?dry_run=true", {
      method: "POST",
      headers: { "X-Admin-Token": adminToken },
      body: fd,
    });

    if (resp.status === 413) {
      _setRosterFeedback("File too large (256 KiB max)", "error");
      pendingRosterFile = null;
      return;
    }

    if (resp.status === 400) {
      const detail = await resp.json().catch(() => ({}));
      const body = detail && detail.detail ? detail.detail : {};
      const rowErrors = Array.isArray(body.errors) ? body.errors : [];
      _setRosterFeedback("Can't ingest malformed CSV file", "error");
      _renderRosterErrors(rowErrors);
      pendingRosterFile = null;
      return;
    }

    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      const msg =
        typeof detail.detail === "string" ? detail.detail : "Server error " + resp.status;
      _setRosterFeedback(msg, "error");
      pendingRosterFile = null;
      return;
    }

    const summary = await resp.json();
    _renderRosterPreview(summary);
    pendingRosterFile = file;
    _setConfirmEnabled(true);
    _setRosterFeedback(
      "Preview OK. Review the lists, then press Confirm replacement to wipe and import.",
      "success"
    );
  } catch (err) {
    _setRosterFeedback("Upload failed: " + err.message, "error");
    pendingRosterFile = null;
  }
});

document.getElementById("roster-confirm-btn").addEventListener("click", async () => {
  if (!pendingRosterFile) {
    _setRosterFeedback("Upload and preview a file first.", "error");
    return;
  }
  if (!confirm("Replace the entire roster? This wipes teams, players, matches, and heat state.")) {
    return;
  }

  const fd = new FormData();
  fd.append("file", pendingRosterFile);

  try {
    const resp = await fetch(API_BASE_URL + "/admin/teams/upload-csv", {
      method: "POST",
      headers: { "X-Admin-Token": adminToken },
      body: fd,
    });

    if (resp.status === 413) {
      _setRosterFeedback("File too large (256 KiB max)", "error");
      return;
    }

    if (resp.status === 400) {
      const detail = await resp.json().catch(() => ({}));
      const body = detail && detail.detail ? detail.detail : {};
      const rowErrors = Array.isArray(body.errors) ? body.errors : [];
      _setRosterFeedback("Can't ingest malformed CSV file", "error");
      _renderRosterErrors(rowErrors);
      return;
    }

    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      const msg =
        typeof detail.detail === "string" ? detail.detail : "Server error " + resp.status;
      _setRosterFeedback(msg, "error");
      return;
    }

    const summary = await resp.json();
    const teamCount = (summary.created_teams || []).length;
    const playerCount = (summary.created_players || []).length;
    _setRosterFeedback(
      `Roster replaced. ${teamCount} teams and ${playerCount} players created.`,
      "success"
    );
    _clearRosterPreview();
    pendingRosterFile = null;
    _setConfirmEnabled(false);
    const input = document.getElementById("roster-csv-file");
    if (input) input.value = "";

    // Refresh every cache-backed view since everything was just replaced.
    await loadTeamsAndPlayers();
    loadAdminTeams();
    loadAdminPlayers();
    loadAdminHeatInfo();
    loadMatches();
    loadLeaderboard();
    loadHeatInfo();
  } catch (err) {
    _setRosterFeedback("Confirm failed: " + err.message, "error");
  }
});

// Initial load
startHeatPolling();
loadCurrentHeat();
loadTeamsAndPlayers().then(_restoreHighlightFromStorage);
