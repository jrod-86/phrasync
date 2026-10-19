"use strict";

// Export window, laid out like CapCut's: a name and folder, then Video, Audio
// and Captions sections that can each be switched on or off. Settings live in
// project.export so every export of this project starts where the last one
// left off.

function exportSettings() {
  const settings = project.export;
  settings.codec ||= "h264";
  settings.format ||= "mp4";
  if (typeof settings.video !== "boolean") settings.video = true;
  settings.audio = { enabled: false, format: "mp3", ...(settings.audio || {}) };
  settings.captions = { enabled: false, format: "srt", ...(settings.captions || {}) };
  return settings;
}

function exportRangeSeconds() {
  const range = project.exportRange;
  return range ? Math.max(0, range.out - range.in) : projectDuration();
}

/** Rough file size: CRF has no fixed rate, so use typical 1080p30 rates and scale. */
function estimatedVideoMbps(settings) {
  if (settings.bitrateMbps != null) return Number(settings.bitrateMbps) || 0;
  const base = { 23: 4, 18: 10, 15: 16 }[settings.crf] ?? 10;
  const scale = (project.canvas.width * project.canvas.height * project.canvas.fps) / (1920 * 1080 * 30);
  return base * Math.max(0.2, scale) * (settings.codec === "hevc" ? 0.6 : 1);
}

function formatSize(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}

function refreshExportSummary() {
  const settings = exportSettings();
  const seconds = exportRangeSeconds();
  const whole = Math.round(seconds);
  let bytes = 0;
  if (settings.video) bytes += seconds * (estimatedVideoMbps(settings) + 0.192) * 125000;
  if (settings.audio.enabled) bytes += seconds * ({ mp3: 320, wav: 1411, aac: 256 }[settings.audio.format] || 320) * 125;
  const nothing = !settings.video && !settings.audio.enabled && !settings.captions.enabled;
  $("#exportSummary").textContent = nothing
    ? "Turn on at least one of Video, Audio or Captions."
    : `Duration ${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")} · Size about ${formatSize(bytes)}`;
  els.confirmRender.disabled = nothing;
  $$(".export-group").forEach(group => {
    const on = group.querySelector(".export-toggle input").checked;
    group.classList.toggle("is-off", !on);
    group.querySelectorAll(".export-grid select, .export-grid input").forEach(control => { control.disabled = !on; });
  });
}

function syncExportDialog() {
  const settings = exportSettings();
  $("#exportName").value = project.title || "";
  $("#exportVideo").checked = settings.video;
  $("#exportCodec").value = settings.codec;
  $("#exportContainer").value = settings.format;
  $("#exportAudio").checked = settings.audio.enabled;
  $("#exportAudioFormat").value = settings.audio.format;
  $("#exportCaptions").checked = settings.captions.enabled;
  $("#exportCaptionFormat").value = settings.captions.format;
  showExportStage("setup");
  refreshExportSummary();
}

/** setup: choosing settings · running: progress · done: result. */
function showExportStage(stage) {
  $("#exportSetup").hidden = stage !== "setup";
  $("#exportRunning").hidden = stage === "setup";
  $("#exportSummary").hidden = stage !== "setup";
  $("#renderTitle").textContent = stage === "setup" ? "Export" : (stage === "running" ? "Exporting…" : "Export complete");
}

function exportResultSummary(result) {
  const names = (result.files || [result.path]).map(path => path.replace(/^.*[\\/]/, ""));
  const video = result.width ? `${result.width} × ${result.height} · ${result.fps} fps · ${result.duration.toFixed(2)}s · ` : "";
  return `${video}${names.join(", ")}`;
}

const exportBindings = [
  ["#exportVideo", "change", target => { exportSettings().video = target.checked; }],
  ["#exportCodec", "change", target => { exportSettings().codec = target.value; }],
  ["#exportContainer", "change", target => { exportSettings().format = target.value; }],
  ["#exportAudio", "change", target => { exportSettings().audio.enabled = target.checked; }],
  ["#exportAudioFormat", "change", target => { exportSettings().audio.format = target.value; }],
  ["#exportCaptions", "change", target => { exportSettings().captions.enabled = target.checked; }],
  ["#exportCaptionFormat", "change", target => { exportSettings().captions.format = target.value; }],
  ["#exportName", "input", target => { project.title = target.value; if (els.projectTitle) els.projectTitle.value = target.value; }]
];
for (const [selector, type, apply] of exportBindings) {
  $(selector).addEventListener(type, event => { apply(event.target); scheduleSave(); refreshExportSummary(); });
}
[els.resolutionSelect, els.fpsSelect].forEach(control => control.addEventListener("change", refreshExportSummary));
