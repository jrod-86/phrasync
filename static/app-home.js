"use strict";

// CapCut-style start page. Every project autosaves into the local project
// library (/api/library) under its own id, so the start page can list them,
// reopen one, or start a new one without losing the current edit.

const HOME_FEATURES = [
  { id: "lyric", title: "Lyric video", text: "Song + lyrics, synced word by word", icon: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>' },
  { id: "subtitles", title: "Subtitles", text: "Transcribe a video and burn in captions", icon: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h4M13 15h4M7 11h10"/>' },
  { id: "vocals", title: "Remove vocals", text: "Make an instrumental for karaoke", icon: '<path d="M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M4 4l16 16"/>' },
  { id: "import", title: "Open project file", text: "Load a .phrasync.json you saved", icon: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="M12 11v5M9.5 13.5 12 16l2.5-2.5"/>' }
];

let homeProjects = [];
let homeSaveTimer = null;
let homeSaving = Promise.resolve();
let homeThumbAt = 0;
let homeDeleted = null;

const newLibraryId = () => `p-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
project.id ||= newLibraryId();

/** Small JPEG of the preview: the visible stage layers plus the lyric on screen. */
function captureThumbnail() {
  try {
    const stage = els.stage.getBoundingClientRect();
    if (stage.width < 8 || stage.height < 8) return null;
    const canvas = document.createElement("canvas");
    canvas.width = 384;
    canvas.height = Math.max(2, Math.round(384 * stage.height / stage.width));
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#08080c"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    for (const layer of [els.visualCanvas, $("#glCanvas"), els.backgroundImage, els.backgroundVideo, $("#footageCanvas"), $("#effectsCanvas")]) {
      if (!layer || layer.hidden || getComputedStyle(layer).display === "none") continue;
      try { ctx.drawImage(layer, 0, 0, canvas.width, canvas.height); } catch { /* not ready */ }
    }
    const cue = project.cues?.find(item => item.id === currentCueId) || project.cues?.[0];
    const text = (cue?.text || "").replace(/\s+/g, " ").trim().slice(0, 60);
    if (text) {
      const word = $(".lyric-word", els.lyricDisplay) || els.lyricDisplay;
      const style = getComputedStyle(word);
      ctx.font = `800 ${Math.round(canvas.height * .13)}px ${style.fontFamily}`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.lineWidth = Math.max(2, canvas.height * .012); ctx.strokeStyle = "rgba(0,0,0,.7)";
      ctx.fillStyle = project.style?.textColor || "#fff";
      const y = canvas.height * (Number(project.style?.positionY) || 52) / 100;
      ctx.strokeText(text, canvas.width / 2, y, canvas.width * .9);
      ctx.fillText(text, canvas.width / 2, y, canvas.width * .9);
    }
    return canvas.toDataURL("image/jpeg", .74);
  } catch {
    return null;
  }
}

/** A new project nobody has touched yet: not worth a card on the start page. */
function isPristineProject() {
  const texts = list => (list || []).map(cue => cue.text).join("|");
  const bg = project.background || {};
  return !project.audioAssetId && !project.sourceAssetId && texts(project.cues) === texts(DEFAULT_PROJECT.cues)
    && bg.type === DEFAULT_PROJECT.background.type && !(bg.clips || []).length
    && ["Untitled lyric video", "Untitled subtitles"].includes(project.title);
}

/** Save the open project into the library now (thumbnail included when asked or due). */
function saveToLibrary(withThumbnail = false) {
  clearTimeout(homeSaveTimer);
  if (isPristineProject()) return homeSaving;
  const id = project.id;
  const body = { project };
  if (withThumbnail || Date.now() - homeThumbAt > 20000) {
    body.thumbnail = captureThumbnail();
    homeThumbAt = Date.now();
  }
  const json = JSON.stringify(body);
  homeSaving = homeSaving.then(() => fetch(`/api/library/${id}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: json
  })).catch(() => { /* the localStorage autosave still has it */ });
  return homeSaving;
}

/** Called from scheduleSave: coalesce rapid edits into one library write. */
function librarySave() {
  refreshOriginalRatio(); refreshRatioButton();
  clearTimeout(homeSaveTimer);
  homeSaveTimer = setTimeout(() => saveToLibrary(), 1500);
}

/** Swap the editor over to another project object. */
function replaceProject(next, message = "") {
  els.audioPlayer.pause();
  project = migrateProject(next);
  project.id ||= newLibraryId();
  analysis = null; analysisPending = false; selectedWordIndex = 0; tapArmed = false; tapQueue = [];
  selectedFootageId = null; currentCueId = null;
  selectedCueId = project.cues[0]?.id || null;
  applyProjectToControls(); updateSyncSummary(); timeline?.fitAll(); seekTo(0); scheduleSave();
  if (message) toast(message, "success");
  if (project.audioAssetId) ensureAnalysis();
}

async function startNewProject(kind = "lyric") {
  await saveToLibrary(true);
  const fresh = applyNewProjectPrefs(clone(DEFAULT_PROJECT));
  fresh.id = newLibraryId();
  fresh.mode = kind === "subtitles" ? "subtitles" : "lyric";
  fresh.title = fresh.mode === "subtitles" ? "Untitled subtitles" : "Untitled lyric video";
  replaceProject(fresh);
  hideHome();
  showSidebar("audio", kind === "vocals" ? "vocals" : "song");
}

async function openLibraryProject(id) {
  if (id === project.id) return hideHome();
  try {
    await saveToLibrary(true);
    const response = await fetch(`/api/library/${id}`);
    if (!response.ok) throw new Error(response.status === 404 ? "it was not found" : `error ${response.status}`);
    replaceProject(await response.json());
    hideHome();
  } catch (error) { toast(`Could not open the project: ${error.message}`, "error"); }
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(seconds || 0));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function formatWhen(stamp) {
  const minutes = Math.round((Date.now() / 1000 - stamp) / 60);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 60 * 24) return `${Math.round(minutes / 60)} h ago`;
  return new Date(stamp * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function renderHomeProjects() {
  const grid = $("#homeProjects");
  const query = $("#homeSearch").value.trim().toLowerCase();
  const sort = $("#homeSort").value;
  const items = homeProjects.filter(item => item.title.toLowerCase().includes(query));
  if (sort === "name") items.sort((a, b) => a.title.localeCompare(b.title));
  $("#homeCount").textContent = homeProjects.length ? `${homeProjects.length}` : "";
  grid.replaceChildren();
  $("#homeEmpty").hidden = items.length > 0;
  $("#homeEmpty").textContent = homeProjects.length ? "No projects match your search." : "No projects yet. Create one to get started.";
  for (const item of items) {
    const card = document.createElement("article");
    card.className = "home-card";
    card.dataset.id = item.id;
    card.tabIndex = 0;
    const thumb = document.createElement("div");
    thumb.className = "home-thumb";
    if (item.thumbnail) {
      const img = document.createElement("img");
      img.src = item.thumbnail; img.alt = ""; img.loading = "lazy";
      thumb.append(img);
    } else {
      thumb.innerHTML = `<span>${item.mode === "subtitles" ? "CC" : "♪"}</span>`;
    }
    const badge = document.createElement("em");
    badge.textContent = formatDuration(item.duration);
    thumb.append(badge);
    const title = document.createElement("strong");
    title.textContent = item.title;
    const meta = document.createElement("small");
    meta.textContent = `${item.aspect === "original" ? "Original" : item.aspect} · ${item.cueCount} lines · ${formatWhen(item.updatedAt)}`;
    const more = document.createElement("button");
    more.type = "button"; more.className = "home-more"; more.textContent = "⋯";
    more.setAttribute("aria-label", `More actions for ${item.title}`);
    card.append(thumb, title, meta, more);
    grid.append(card);
  }
}

async function refreshHome() {
  try {
    const response = await fetch("/api/library");
    homeProjects = (await response.json()).projects || [];
  } catch { homeProjects = []; }
  renderHomeProjects();
}

async function showHome() {
  els.audioPlayer.pause();
  closeHomeMenu();
  await saveToLibrary(true);
  document.body.classList.add("home-open");
  $("#homePage").hidden = false;
  await refreshHome();
}

function hideHome() {
  $("#homePage").hidden = true;
  document.body.classList.remove("home-open");
  timeline?.resize?.();
}

function closeHomeMenu() { $("#homeCardMenu").hidden = true; }

function openHomeMenu(card, anchor) {
  const menu = $("#homeCardMenu");
  menu.dataset.id = card.dataset.id;
  const box = anchor.getBoundingClientRect();
  menu.style.left = `${Math.min(innerWidth - 180, box.left)}px`;
  menu.style.top = `${box.bottom + 4}px`;
  menu.hidden = false;
}

async function homeAction(action, id) {
  const item = homeProjects.find(entry => entry.id === id);
  if (!item) return;
  if (action === "open") return openLibraryProject(id);
  if (action === "rename") {
    const title = prompt("Project name", item.title)?.trim();
    if (!title || title === item.title) return;
    if (id === project.id) { project.title = title; els.projectTitle.value = title; await saveToLibrary(); }
    else {
      const loaded = await (await fetch(`/api/library/${id}`)).json();
      await fetch(`/api/library/${id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project: { ...loaded, title: title.slice(0, 80) } }) });
    }
  }
  if (action === "duplicate") await fetch(`/api/library/${id}/duplicate`, { method: "POST" });
  if (action === "delete") {
    await homeSaving;
    await fetch(`/api/library/${id}`, { method: "DELETE" });
    homeDeleted = item;
    // Keep autosave from writing the deleted project straight back.
    if (id === project.id) { const fresh = clone(DEFAULT_PROJECT); fresh.id = newLibraryId(); replaceProject(fresh); }
    $("#homeUndoText").textContent = `Deleted “${item.title}”.`;
    $("#homeUndo").hidden = false;
  }
  await refreshHome();
}

function initHome() {
  const features = $("#homeFeatures");
  for (const feature of HOME_FEATURES) {
    const button = document.createElement("button");
    button.type = "button"; button.className = "home-feature"; button.dataset.feature = feature.id;
    button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${feature.icon}</svg><span><strong></strong><small></small></span>`;
    $("strong", button).textContent = feature.title;
    $("small", button).textContent = feature.text;
    features.append(button);
  }
  features.addEventListener("click", event => {
    const id = event.target.closest(".home-feature")?.dataset.feature;
    if (id === "import") { startNewProject("lyric").then(() => els.loadProjectButton.click()); }
    else if (id) startNewProject(id);
  });
  $("#homeCreate").addEventListener("click", () => startNewProject("lyric"));
  $("#homeSearch").addEventListener("input", renderHomeProjects);
  $("#homeSort").addEventListener("change", renderHomeProjects);
  const grid = $("#homeProjects");
  grid.addEventListener("click", event => {
    const card = event.target.closest(".home-card");
    if (!card) return;
    const more = event.target.closest(".home-more");
    if (more) { event.stopPropagation(); openHomeMenu(card, more); return; }
    openLibraryProject(card.dataset.id);
  });
  grid.addEventListener("contextmenu", event => {
    const card = event.target.closest(".home-card");
    if (!card) return;
    event.preventDefault();
    openHomeMenu(card, { getBoundingClientRect: () => ({ left: event.clientX, bottom: event.clientY }) });
  });
  grid.addEventListener("keydown", event => {
    const card = event.target.closest(".home-card");
    if (card && event.key === "Enter") openLibraryProject(card.dataset.id);
  });
  $("#homeCardMenu").addEventListener("click", event => {
    const action = event.target.closest("button")?.dataset.action;
    const id = $("#homeCardMenu").dataset.id;
    closeHomeMenu();
    if (action) homeAction(action, id).catch(error => toast(error.message, "error"));
  });
  document.addEventListener("pointerdown", event => { if (!event.target.closest("#homeCardMenu, .home-more")) closeHomeMenu(); });
  $("#homeUndo button").addEventListener("click", async () => {
    $("#homeUndo").hidden = true;
    if (homeDeleted) await fetch(`/api/library/${homeDeleted.id}/restore`, { method: "POST" });
    homeDeleted = null;
    await refreshHome();
  });
  $("#homeSettings").addEventListener("click", () => openSettings());
  $("#homeDiagnostics").addEventListener("click", () => $("#diagnosticsButton").click());
  $("#homeTheme").addEventListener("click", () => els.themeToggle.click());
  addEventListener("pagehide", () => saveToLibrary());
  if (appPrefs.startPage) showHome();
}

document.addEventListener("DOMContentLoaded", initHome, { once: true });
