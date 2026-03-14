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
      timerLabel.textContent = "Get Ready!";
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
      timerLabel.textContent = "Time Remaining";
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
    if (btn.dataset.tab === "scoreboard") loadLeaderboard();
    if (btn.dataset.tab === "matches") loadMatches();
    if (btn.dataset.tab === "teams") loadTeams();
    if (btn.dataset.tab === "nextheat") startHeatPolling();
    else stopHeatPolling();
    if (btn.dataset.tab === "admin") loadAdminHeatInfo();
    if (btn.dataset.tab === "register") {
      populateTeamDropdowns();
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
  const medals = ["\u{1F947}", "\u{1F948}", "\u{1F949}"]; // gold, silver, bronze
  tbody.innerHTML = entries
    .map(
      (e, i) => `
    <tr>
      <td>${i < 3 ? medals[i] : i + 1}</td>
      <td>${escapeHtml(e.team_name)}</td>
      <td>${e.total_wins}</td>
      <td>${e.total_loss}</td>
      <td>${e.total_score}</td>
      <td>${e.total_matches}</td>
    </tr>`
    )
    .join("");
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
        const redPts = m.team2_points;
        const blueName = m.team1_name;
        const bluePts = m.team1_points;
        const redScore = m.team2_score;
        const blueScore = m.team1_score;

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
  if (!confirm("This will setup the next heat (advance heat number and generate new matchups). Continue?")) return;

  try {
    const resp = await fetch(API_BASE_URL + "/heat/start-next", {
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
    const durationSelect = document.getElementById("timer-duration");
    if (durationSelect) {
      durationSelect.value = String(data.timer_duration);
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
    loadAdminTeams();
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

// ── Admin: Add Team ───────────────────────────────────────────────────

document.getElementById("add-team-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const name = document.getElementById("new-team-name").value.trim();
  const m1 = document.getElementById("new-team-member1").value.trim();
  const m2 = document.getElementById("new-team-member2").value.trim();
  const m3 = document.getElementById("new-team-member3").value.trim();

  if (!name || !m1 || !m2) {
    showError("Team name and at least 2 members are required");
    return;
  }

  const members = [m1, m2];
  if (m3) members.push(m3);

  try {
    const resp = await fetch(API_BASE_URL + "/teams", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ name, members }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    document.getElementById("add-team-form").reset();
    const msg = document.getElementById("add-team-success");
    msg.classList.remove("hidden");
    setTimeout(() => msg.classList.add("hidden"), 3000);
    loadAdminTeams();
  } catch (err) {
    showError("Failed to add team: " + err.message);
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
      (t, i) => `
    <tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(t.name)}</td>
      <td>${t.members.map(escapeHtml).join(", ")}</td>
      <td><button class="btn-delete" onclick="deleteTeam('${t.id}')">✕</button></td>
    </tr>`
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
    loadAdminTeams();
  } catch (err) {
    showError("Failed to delete team: " + err.message);
  }
}

// ── Admin: Timer Duration ──────────────────────────────────────────────

document.getElementById("save-timer-btn").addEventListener("click", async () => {
  const seconds = parseInt(document.getElementById("timer-duration").value, 10);
  try {
    const resp = await fetch(API_BASE_URL + "/heat/timer-duration", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Admin-Token": adminToken },
      body: JSON.stringify({ seconds }),
    });
    if (!resp.ok) {
      const detail = await resp.json().catch(() => ({}));
      throw new Error(detail.detail || "Server error " + resp.status);
    }
    const btn = document.getElementById("save-timer-btn");
    btn.textContent = "Saved!";
    setTimeout(() => { btn.textContent = "Save Timer Duration"; }, 2000);
  } catch (err) {
    showError("Failed to save timer duration: " + err.message);
  }
});

// Initial load
startHeatPolling();
populateTeamDropdowns();
loadCurrentHeat();
