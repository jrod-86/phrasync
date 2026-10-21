"use strict";

// Drag a file from Explorer onto the "Add song" box (Audio tab) or the
// background picture/video box (Background tab) instead of browsing for it.

const SONG_FILE = /\.(wav|mp3|m4a|aac|flac|ogg|opus|aif|aiff|wma)$/i;
const IMAGE_FILE = /\.(png|jpe?g|webp|bmp|tiff?)$/i;
const VIDEO_FILE = /\.(mp4|webm)$/i;

function draggingFiles(event) {
  return [...(event.dataTransfer?.types || [])].includes("Files");
}

/** Make a tile accept a dropped file; `check` returns an error message or "". */
function makeDropTile(tile, check, handle) {
  let depth = 0;
  const clear = () => { depth = 0; tile.classList.remove("drop-active"); };
  tile.addEventListener("dragenter", event => {
    if (!draggingFiles(event)) return;
    event.preventDefault(); depth += 1;
    tile.dataset.dropLabel = t("Drop to add"); tile.classList.add("drop-active");
  });
  tile.addEventListener("dragover", event => {
    if (!draggingFiles(event)) return;
    event.preventDefault(); event.dataTransfer.dropEffect = "copy";
  });
  tile.addEventListener("dragleave", () => { depth = Math.max(0, depth - 1); if (!depth) clear(); });
  tile.addEventListener("drop", event => {
    if (!draggingFiles(event)) return;
    event.preventDefault(); event.stopPropagation(); clear();
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const problem = check(file);
    if (problem) { toast(t(problem), "error"); return; }
    handle(file);
  });
}

function initDropTiles() {
  makeDropTile(els.audioPick,
    file => SONG_FILE.test(file.name) || file.type.startsWith("audio/") ? "" : "Drop a song file here (WAV, MP3, FLAC, M4A…).",
    file => handleAudioFile(file));
  makeDropTile(els.backgroundPick, file => {
    const type = project.background.type;
    if (type === "image") return IMAGE_FILE.test(file.name) ? "" : "Drop a picture here (PNG, JPG, WEBP).";
    if (type === "video") return VIDEO_FILE.test(file.name) ? "" : "Drop an MP4 or WebM video here.";
    return "Choose Picture or Video as the background first.";
  }, file => handleBackgroundFile(file));
  // A file dropped anywhere else must not make the window open it and leave the editor.
  for (const name of ["dragover", "drop"]) {
    window.addEventListener(name, event => { if (draggingFiles(event)) event.preventDefault(); });
  }
}

initDropTiles();
