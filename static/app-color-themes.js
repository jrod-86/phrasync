"use strict";

// One-click colour themes for the lyric text. A theme only fills in the four
// existing colour pickers, so preview, export and manual tweaks all keep
// working through the same style values.

const COLOR_THEMES = [
  ["Phrasync Neon", "#ffffff", "#ff3d7f", "#8f5bff", "#05040c"],
  ["Classic Karaoke", "#ffffff", "#2f7bff", "#00d4ff", "#000000"],
  ["Golden Hour", "#fff4e0", "#ffb627", "#ff6b35", "#2b1400"],
  ["Fire", "#fff1d6", "#ff4500", "#ffae00", "#1a0000"],
  ["Ice", "#e8f7ff", "#5ad1ff", "#a6f0ff", "#03131f"],
  ["Synthwave", "#ffe6ff", "#ff2bd6", "#00f0ff", "#1a0033"],
  ["Vaporwave", "#fdf6ff", "#ff71ce", "#01cdfe", "#2d1b4e"],
  ["Matrix", "#c8ffd4", "#00ff41", "#008f11", "#000000"],
  ["Blood Metal", "#e6e6e6", "#c1121f", "#780000", "#000000"],
  ["Gold & Black", "#f5f5f5", "#d4af37", "#ffd700", "#000000"],
  ["Ocean", "#e0f7fa", "#00b4d8", "#0077b6", "#001219"],
  ["Sunset", "#fff0e6", "#ff5e62", "#ff9966", "#2a0a12"],
  ["Pastel Pop", "#ffffff", "#ffadad", "#a0c4ff", "#5a4a6b"],
  ["Bubblegum", "#ffffff", "#ff69b4", "#ffd1dc", "#4a0026"],
  ["Lime Punch", "#ffffff", "#a3ff12", "#00e5a0", "#0b1a00"],
  ["Royal Purple", "#f3e8ff", "#9d4edd", "#e0aaff", "#10002b"],
  ["Toxic", "#eaffd0", "#c6ff00", "#76ff03", "#1b1b00"],
  ["Desert Rock", "#f4ead5", "#c8553d", "#f28f3b", "#2d1e12"],
  ["Electric Orange", "#ffffff", "#ff8c00", "#1e90ff", "#000814"],
  ["Ink on Paper", "#111111", "#e63946", "#457b9d", "#ffffff"]
];
const THEME_KEYS = ["textColor", "accentColor", "accentColor2", "strokeColor"];

function matchingColorTheme(style) {
  const current = THEME_KEYS.map(key => String(style[key] || "").toLowerCase());
  return COLOR_THEMES.findIndex(theme => theme.slice(1).every((color, index) => color === current[index]));
}

function syncColorTheme() {
  const select = $("#colorTheme");
  if (select) select.value = String(matchingColorTheme(project.style));
}

function applyColorTheme(index) {
  const theme = COLOR_THEMES[index];
  if (!theme) return;
  THEME_KEYS.forEach((key, position) => {
    els[key].value = theme[position + 1];
    els[key].dispatchEvent(new Event("input", { bubbles: true }));
  });
}

(function setUpColorThemes() {
  const select = $("#colorTheme");
  if (!select) return;
  select.replaceChildren(new Option("Custom colours", "-1"),
    ...COLOR_THEMES.map(([name], index) => new Option(name, String(index))));
  select.addEventListener("change", () => applyColorTheme(Number(select.value)));
  THEME_KEYS.forEach(key => els[key].addEventListener("input", syncColorTheme));
  syncColorTheme();
})();
