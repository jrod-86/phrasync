"use strict";

// CapCut-style Settings window: Projects, Edit, Performance, General and About
// tabs, edited as a draft and applied with Save. Preferences live in the
// workspace settings.json (/api/settings/preferences) and are cached in
// localStorage so the start page and shortcuts can read them at launch.

const PREFS_KEY = "phrasync.prefs";
const PREF_DEFAULTS = {
  exportDirectory: null, exportThreads: 0, stepSeconds: 1, imageDuration: 5,
  newAspect: "original", newResolution: 1080, newFps: 30, defaultEncoder: "cpu",
  exportSound: true, startPage: true
};

let appPrefs = { ...PREF_DEFAULTS };
try { appPrefs = { ...PREF_DEFAULTS, ...JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") }; } catch { /* storage blocked */ }
let cpuCount = 4;

function storePrefs(prefs) {
  appPrefs = { ...PREF_DEFAULTS, ...prefs };
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(appPrefs)); } catch { /* storage blocked */ }
}

async function loadPrefs() {
  try {
    const result = await api("/api/settings/preferences");
    cpuCount = result.cpuCount || cpuCount;
    storePrefs(result.preferences);
  } catch { /* keep the cached copy */ }
}

/** Short two-note chime when an export finishes. */
function playExportSound() {
  if (!appPrefs.exportSound) return;
  try {
    const context = new AudioContext();
    [[880, 0], [1320, .16]].forEach(([frequency, at]) => {
      const tone = context.createOscillator(), gain = context.createGain();
      tone.frequency.value = frequency; tone.type = "sine";
      gain.gain.setValueAtTime(0, context.currentTime + at);
      gain.gain.linearRampToValueAtTime(.18, context.currentTime + at + .02);
      gain.gain.exponentialRampToValueAtTime(.001, context.currentTime + at + .45);
      tone.connect(gain).connect(context.destination);
      tone.start(context.currentTime + at); tone.stop(context.currentTime + at + .5);
    });
    setTimeout(() => context.close(), 1200);
  } catch { /* no audio device */ }
}

/** Apply the "new projects start with" choices to a fresh project. */
function applyNewProjectPrefs(fresh) {
  fresh.canvas.aspect = appPrefs.newAspect;
  fresh.canvas.fps = appPrefs.newFps;
  [fresh.canvas.width, fresh.canvas.height] = canvasSize(appPrefs.newAspect, appPrefs.newResolution);
  fresh.export = { ...(fresh.export || {}), encoder: appPrefs.defaultEncoder };
  return fresh;
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const power = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** power).toFixed(power ? 1 : 0)} ${units[power]}`;
}

function showSettingsTab(name) {
  $$("#settingsDialog [data-set-tab]").forEach(tab => tab.classList.toggle("active", tab.dataset.setTab === name));
  $$("#settingsDialog [data-set-page]").forEach(page => { page.hidden = page.dataset.setPage !== name; });
}

async function refreshStorage() {
  try {
    const storage = await api("/api/settings/storage");
    $("#set-projects-path").textContent = storage.projects.path;
    $("#set-projects-path").title = storage.projects.path;
    $("#set-projects-size").textContent = `${formatBytes(storage.projects.bytes)} used.`;
    const exportPath = appPrefs.exportDirectory || (storage.exports.chosen ? storage.exports.path : "");
    $("#set-exports-path").textContent = exportPath || "Not chosen yet (asked on first export)";
    $("#set-exports-path").title = exportPath;
    $("#setExportInput").value = appPrefs.exportDirectory || "";
    $("#set-temp-size").textContent = formatBytes(storage.temp.bytes);
    $("#set-models-size").textContent = formatBytes(storage.models.bytes);
    $("#set-uploads-size").textContent = formatBytes(storage.uploads.bytes);
  } catch { /* sizes stay as … */ }
}

async function fillSettingsEncoders() {
  const select = $("#setEncoder");
  try {
    const { gpus } = await api("/api/gpus");
    select.replaceChildren(new Option("CPU", "cpu"), ...gpus.map(gpu => new Option(`GPU ${gpu.index}: ${gpu.name}`, `gpu:${gpu.index}`)));
  } catch { /* CPU only */ }
  select.value = [...select.options].some(option => option.value === appPrefs.defaultEncoder) ? appPrefs.defaultEncoder : "cpu";
}

/** Load the current values into the form each time Settings opens. */
async function fillSettings(tab) {
  await loadPrefs();
  $("#setStep").value = appPrefs.stepSeconds;
  $("#setImageDuration").value = appPrefs.imageDuration;
  $("#setAspect").value = appPrefs.newAspect;
  $("#setResolution").value = String(appPrefs.newResolution);
  $("#setFps").value = String(appPrefs.newFps);
  $("#setSound").checked = appPrefs.exportSound;
  $("#setStartPage").checked = appPrefs.startPage;
  $("#setGuide").checked = localStorage.getItem(ONBOARDING_KEY) !== "hidden";
  const threads = $("#setThreads");
  threads.replaceChildren(new Option(`Auto (${Math.max(1, Math.min(32, cpuCount - 1))})`, "0"),
    ...Array.from({ length: Math.min(64, cpuCount) }, (_, index) => new Option(String(index + 1), String(index + 1))));
  threads.value = String(appPrefs.exportThreads || 0);
  $$('input[name="setLanguage"]').forEach(input => { input.checked = input.value === currentLanguage; });
  $$('input[name="setTheme"]').forEach(input => { input.checked = input.value === (els.root.dataset.theme || "dark"); });
  $("#setExportChoose").hidden = !IS_DESKTOP_HOST;
  $("#setExportInput").hidden = IS_DESKTOP_HOST;
  $$("#settingsDialog [data-open-folder]").forEach(button => { button.hidden = !IS_DESKTOP_HOST; });
  if (tab) showSettingsTab(tab);
  fillSettingsEncoders();
  refreshStorage();
}

async function saveSettings() {
  const number = (selector, fallback) => Number($(selector).value) || fallback;
  const changes = {
    stepSeconds: number("#setStep", 1),
    imageDuration: number("#setImageDuration", 5),
    newAspect: $("#setAspect").value,
    newResolution: number("#setResolution", 1080),
    newFps: number("#setFps", 30),
    exportSound: $("#setSound").checked,
    startPage: $("#setStartPage").checked,
    defaultEncoder: $("#setEncoder").value,
    exportThreads: Number($("#setThreads").value) || 0
  };
  if (!IS_DESKTOP_HOST) changes.exportDirectory = $("#setExportInput").value.trim() || null;
  try {
    const result = await api("/api/settings/preferences", {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preferences: changes })
    });
    storePrefs(result.preferences);
  } catch (error) { toast(`Could not save settings: ${error.message}`, "error"); return; }
  if ($("#setGuide").checked) localStorage.removeItem(ONBOARDING_KEY); else localStorage.setItem(ONBOARDING_KEY, "hidden");
  const language = $('input[name="setLanguage"]:checked')?.value;
  if (language && language !== currentLanguage) $("#languageToggle").click();
  const theme = $('input[name="setTheme"]:checked')?.value;
  if (theme && theme !== (els.root.dataset.theme || "dark")) els.themeToggle.click();
  els.settingsDialog.close();
  toast("Settings saved.", "success");
}

function initSettingsWindow() {
  $$("#settingsDialog [data-set-tab]").forEach(tab => tab.addEventListener("click", () => showSettingsTab(tab.dataset.setTab)));
  $("#settingsSave").addEventListener("click", saveSettings);
  $("#setTempClear").addEventListener("click", async () => {
    try {
      const { freed } = await api("/api/settings/clear-temp", { method: "POST" });
      toast(`Cleared ${formatBytes(freed)} of temporary files.`, "success");
      refreshStorage();
    } catch (error) { toast(error.message, "error"); }
  });
  $("#setExportChoose").addEventListener("click", async () => {
    try {
      const directory = await desktopExportApi().choose_render_directory();
      if (!directory) return;
      selectedRenderDirectory = directory;
      storePrefs({ ...appPrefs, exportDirectory: directory });
      refreshStorage();
    } catch (error) { toast(error.message, "error"); }
  });
  $("#settingsDialog").addEventListener("click", async event => {
    const kind = event.target.closest("[data-open-folder]")?.dataset.openFolder;
    if (!kind) return;
    try { await desktopExportApi().open_workspace_folder(kind); } catch (error) { toast(error.message, "error"); }
  });
  loadPrefs();
}

initSettingsWindow();
