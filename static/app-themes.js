"use strict";

// Interface themes: 16 presets, each a light or dark base plus its own
// colours. Picked from the palette button in the top bar, the start page, or
// Settings › General. Only the editor's look changes, never the video.

const UI_THEME_KEY = "phrasync.uiTheme";
const UI_THEMES = [
  { id: "phrasync-dark", name: "Phrasync Dark", base: "dark", bg: "#101112", elevated: "#151618", panel: "#191a1d", panel2: "#202125", panel3: "#292b30", border: "#3a3b42", soft: "#2c2e33", text: "#f4f1f8", muted: "#aaa9b2", accent: "#e487cd", accent2: "#b67ce0" },
  { id: "phrasync-light", name: "Phrasync Light", base: "light", bg: "#efedf3", elevated: "#f8f7fa", panel: "#ffffff", panel2: "#f5f3f8", panel3: "#eeebf2", border: "#d9d4df", soft: "#e6e1e9", text: "#1d1a24", muted: "#686371", accent: "#c04aa8", accent2: "#8f4fd0" },
  { id: "capcut", name: "Studio Cyan", base: "dark", bg: "#0d0e10", elevated: "#141518", panel: "#18191c", panel2: "#212226", panel3: "#2a2c31", border: "#393b41", soft: "#2a2c30", text: "#f2f4f5", muted: "#a2a6ad", accent: "#00c4cc", accent2: "#20e3b2" },
  { id: "midnight", name: "Midnight Blue", base: "dark", bg: "#0b0f1a", elevated: "#10162a", panel: "#131a30", panel2: "#1a2240", panel3: "#222c4f", border: "#323e66", soft: "#232c4c", text: "#eef2ff", muted: "#9aa6c8", accent: "#5aa9ff", accent2: "#7c6cff" },
  { id: "synthwave", name: "Neon Synthwave", base: "dark", bg: "#120b1f", elevated: "#180f2a", panel: "#1d1233", panel2: "#261843", panel3: "#301f53", border: "#46306f", soft: "#2f2050", text: "#fbefff", muted: "#b9a3d6", accent: "#ff2fd0", accent2: "#00e5ff" },
  { id: "ember", name: "Ember", base: "dark", bg: "#15100e", elevated: "#1c1512", panel: "#211915", panel2: "#2b201b", panel3: "#362821", border: "#4d3a30", soft: "#33261f", text: "#fff3ea", muted: "#c3a999", accent: "#ff7a3d", accent2: "#ffb347" },
  { id: "forest", name: "Forest", base: "dark", bg: "#0d1410", elevated: "#121b16", panel: "#15201a", panel2: "#1c2a22", panel3: "#24352b", border: "#344a3c", soft: "#22322a", text: "#effaf2", muted: "#9fb8a8", accent: "#4ade80", accent2: "#a3e635" },
  { id: "ocean", name: "Deep Ocean", base: "dark", bg: "#0a1416", elevated: "#0f1c1f", panel: "#122326", panel2: "#182d31", panel3: "#1f383d", border: "#2d4f55", soft: "#1e3438", text: "#eafcfc", muted: "#94b9bc", accent: "#2dd4bf", accent2: "#38bdf8" },
  { id: "crimson", name: "Crimson Stage", base: "dark", bg: "#140c0e", elevated: "#1b1013", panel: "#211417", panel2: "#2b1a1e", panel3: "#362126", border: "#4f3036", soft: "#341f24", text: "#fff0f2", muted: "#c79ea6", accent: "#ff3b5c", accent2: "#ff8fa3" },
  { id: "gold", name: "Gold Record", base: "dark", bg: "#12100a", elevated: "#19160e", panel: "#1e1a11", panel2: "#282316", panel3: "#332c1c", border: "#4a412a", soft: "#302a1b", text: "#fdf8e9", muted: "#bfb18f", accent: "#f5c542", accent2: "#e8933d" },
  { id: "graphite", name: "Graphite", base: "dark", bg: "#0f0f10", elevated: "#151516", panel: "#19191b", panel2: "#212123", panel3: "#2a2a2d", border: "#3b3b3f", soft: "#2b2b2e", text: "#f5f5f5", muted: "#a5a5aa", accent: "#e6e6e6", accent2: "#9a9aa0" },
  { id: "oled", name: "OLED Black", base: "dark", bg: "#000000", elevated: "#060606", panel: "#0b0b0c", panel2: "#121214", panel3: "#1a1a1d", border: "#2b2b30", soft: "#1b1b1f", text: "#ffffff", muted: "#9c9ca4", accent: "#b388ff", accent2: "#ff80ab" },
  { id: "lavender", name: "Lavender Mist", base: "light", bg: "#f1eef8", elevated: "#f8f6fc", panel: "#ffffff", panel2: "#f4f1fa", panel3: "#ebe6f5", border: "#d8d0ea", soft: "#e6e0f2", text: "#221b33", muted: "#6c6382", accent: "#7c4ddb", accent2: "#c084fc" },
  { id: "paper", name: "Paper", base: "light", bg: "#f4efe6", elevated: "#f9f6f0", panel: "#fffdf9", panel2: "#f7f2ea", panel3: "#efe8dc", border: "#ddd2c0", soft: "#e9e0d2", text: "#2b241b", muted: "#75695a", accent: "#c2410c", accent2: "#d97706" },
  { id: "mint", name: "Mint", base: "light", bg: "#edf6f2", elevated: "#f5faf8", panel: "#ffffff", panel2: "#f1f8f5", panel3: "#e5f1ec", border: "#cde3da", soft: "#deede7", text: "#15241e", muted: "#5a7268", accent: "#0f9f7a", accent2: "#14a3b8" },
  { id: "rose", name: "Rose Quartz", base: "light", bg: "#f8eef2", elevated: "#fbf5f7", panel: "#ffffff", panel2: "#faf2f5", panel3: "#f3e6ec", border: "#e7d0da", soft: "#f0e0e7", text: "#2d1a22", muted: "#7a5e69", accent: "#d02670", accent2: "#f472b6" }
];

function uiTheme(id) {
  return UI_THEMES.find(theme => theme.id === id) || UI_THEMES[0];
}

function currentUiThemeId() {
  try {
    const saved = localStorage.getItem(UI_THEME_KEY);
    if (saved) return uiTheme(saved).id;
    return localStorage.getItem(THEME_KEY) === "light" ? "phrasync-light" : "phrasync-dark";
  } catch { return "phrasync-dark"; }
}

/** Readable text colour on top of an accent-filled button. */
function onAccentColor(hex) {
  const [r, g, b] = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255);
  const light = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return light > 0.45 ? "#15121a" : "#ffffff";
}

function applyUiTheme(id, remember = true) {
  const theme = uiTheme(id);
  const root = document.documentElement;
  root.dataset.theme = theme.base;
  root.dataset.uiTheme = theme.id;
  const vars = {
    "--bg": theme.bg, "--bg-elevated": theme.elevated, "--panel": theme.panel, "--panel-2": theme.panel2,
    "--panel-3": theme.panel3, "--border": theme.border, "--border-soft": theme.soft, "--text": theme.text,
    "--muted": theme.muted, "--muted-2": `color-mix(in srgb, ${theme.muted} 80%, ${theme.bg})`,
    "--accent": theme.accent, "--accent-2": theme.accent2, "--on-accent": onAccentColor(theme.accent),
    "--accent-soft": `color-mix(in srgb, ${theme.accent} ${theme.base === "light" ? 12 : 16}%, transparent)`
  };
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
  if (remember) {
    try { localStorage.setItem(UI_THEME_KEY, theme.id); localStorage.setItem(THEME_KEY, theme.base); } catch { /* storage blocked */ }
  }
  timeline?.refreshTheme?.();
  $$(".theme-swatch").forEach(swatch => swatch.classList.toggle("active", swatch.dataset.uiTheme === theme.id));
}

function themeSwatch(theme) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "theme-swatch";
  button.dataset.uiTheme = theme.id;
  button.title = theme.name;
  button.innerHTML = `<span class="theme-preview" style="background:${theme.bg}">
      <i style="background:${theme.panel};border-color:${theme.soft}"></i>
      <i style="background:${theme.panel2};border-color:${theme.soft}"><b style="background:${theme.accent}"></b><b style="background:${theme.accent2}"></b></i>
    </span><span class="theme-name"></span>`;
  $(".theme-name", button).textContent = theme.name;
  return button;
}

function fillThemeGrid(grid, onPick) {
  grid.replaceChildren(...UI_THEMES.map(themeSwatch));
  grid.addEventListener("click", event => {
    const id = event.target.closest(".theme-swatch")?.dataset.uiTheme;
    if (id) onPick(id);
  });
}

function closeThemePicker() { $("#themePicker").hidden = true; }

/** The quick picker under the palette button (or any other anchor). */
function openThemePicker(anchor) {
  const picker = $("#themePicker");
  if (!picker.hidden) return closeThemePicker();
  const box = anchor.getBoundingClientRect();
  picker.hidden = false;
  const width = picker.offsetWidth;
  picker.style.left = `${Math.max(8, Math.min(innerWidth - width - 8, box.right - width))}px`;
  picker.style.top = `${Math.min(innerHeight - picker.offsetHeight - 8, box.bottom + 8)}px`;
  if (box.left < 300) picker.style.left = `${box.right + 8}px`;
  applyUiTheme(currentUiThemeId(), false);
}

function initThemes() {
  const picker = document.createElement("div");
  picker.id = "themePicker"; picker.className = "theme-picker"; picker.hidden = true;
  picker.innerHTML = '<header><strong>Theme</strong><button type="button" data-theme-more>More settings</button></header><div class="theme-grid"></div>';
  document.body.append(picker);
  fillThemeGrid($(".theme-grid", picker), id => applyUiTheme(id));
  $("[data-theme-more]", picker).addEventListener("click", () => {
    closeThemePicker();
    openSettings().then(() => showSettingsTab("general"));
  });
  document.addEventListener("pointerdown", event => {
    if (!event.target.closest("#themePicker, #themeToggle, #homeTheme, .app-menu")) closeThemePicker();
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeThemePicker(); });
  fillThemeGrid($("#setThemeGrid"), id => { settingsThemePick = id; applyUiTheme(id, false); });
  $("#homeTheme").addEventListener("click", event => openThemePicker(event.currentTarget));
  applyUiTheme(currentUiThemeId());
}

initThemes();
