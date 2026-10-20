"use strict";

// Interface themes: 20 colour families, each in a dark and a light version.
// The sun/moon switch in the top bar flips between them; the palette button,
// the start page and Settings › General pick the family. Only the editor's
// look changes, never the video. A theme is stored as "family:mode".

const UI_THEME_KEY = "phrasync.uiTheme";
const UI_THEMES = [
  { id: "phrasync", name: "Phrasync", hue: 300, tint: 6, cleanLight: true, accent: "#e487cd", accent2: "#b67ce0" },
  { id: "capcut", name: "Studio Cyan", hue: 200, tint: 6, cleanLight: true, accent: "#00c4cc", accent2: "#20e3b2" },
  { id: "midnight", name: "Midnight Blue", hue: 225, tint: 32, accent: "#5aa9ff", accent2: "#7c6cff" },
  { id: "synthwave", name: "Neon Synthwave", hue: 272, tint: 38, accent: "#ff2fd0", accent2: "#00e5ff" },
  { id: "ember", name: "Ember", hue: 18, tint: 22, accent: "#ff7a3d", accent2: "#ffb347" },
  { id: "forest", name: "Forest", hue: 145, tint: 22, accent: "#4ade80", accent2: "#a3e635" },
  { id: "ocean", name: "Deep Ocean", hue: 188, tint: 32, accent: "#2dd4bf", accent2: "#38bdf8" },
  { id: "crimson", name: "Crimson Stage", hue: 350, tint: 26, accent: "#ff3b5c", accent2: "#ff8fa3" },
  { id: "gold", name: "Gold Record", hue: 44, tint: 26, accent: "#f5c542", accent2: "#e8933d" },
  { id: "graphite", name: "Graphite", hue: 0, tint: 0, accent: "#e6e6e6", accent2: "#9a9aa0", lightAccent: "#2f2f35", lightAccent2: "#7a7a82" },
  { id: "oled", name: "OLED / Pure", hue: 260, tint: 0, accent: "#b388ff", accent2: "#ff80ab", pure: true },
  { id: "lavender", name: "Lavender", hue: 262, tint: 26, accent: "#b794f6", accent2: "#f0abfc" },
  { id: "coffee", name: "Coffee", hue: 28, tint: 18, accent: "#d4a373", accent2: "#e9c46a" },
  { id: "mint", name: "Mint", hue: 160, tint: 20, accent: "#5eead4", accent2: "#86efac" },
  { id: "sky", name: "Sky", hue: 206, tint: 30, accent: "#38bdf8", accent2: "#818cf8" },
  { id: "rose", name: "Rose Quartz", hue: 335, tint: 22, accent: "#f472b6", accent2: "#fda4af" },
  { id: "sunset", name: "Sunset", hue: 12, tint: 24, accent: "#ff6b6b", accent2: "#feca57" },
  { id: "aurora", name: "Aurora", hue: 172, tint: 24, accent: "#34d399", accent2: "#a78bfa" },
  { id: "sakura", name: "Cherry Blossom", hue: 330, tint: 16, accent: "#ff9ecd", accent2: "#c4b5fd" },
  { id: "terminal", name: "Retro Terminal", hue: 125, tint: 30, accent: "#39ff14", accent2: "#00ff9c" }
];
// Themes saved by the earlier 16-theme version.
const LEGACY_UI_THEMES = {
  "phrasync-dark": "phrasync:dark", "phrasync-light": "phrasync:light", paper: "coffee:light",
  lavender: "lavender:light", mint: "mint:light", rose: "rose:light"
};

const hsl = (h, s, l) => `hsl(${h} ${s}% ${l}%)`;

function hexToHsl(hex) {
  const [r, g, b] = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  if (max === min) return [0, 0, l * 100];
  const d = max - min, s = d / (1 - Math.abs(2 * l - 1));
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [Math.round((h * 60 + 360) % 360), Math.round(s * 100), Math.round(l * 100)];
}

/** On a light background an accent needs to be darker to stay readable. */
function lightAccent(hex) {
  const [h, s, l] = hexToHsl(hex);
  return hsl(h, Math.min(90, s), Math.min(l, 42));
}

function themeColors(family, mode) {
  const { hue: h, tint: t } = family;
  if (mode === "light") {
    const accents = { accent: family.lightAccent || lightAccent(family.accent), accent2: family.lightAccent2 || lightAccent(family.accent2) };
    if (family.pure || family.cleanLight || !t) {
      // Clean white light themes: Phrasync, Studio Cyan, Pure (and grey Graphite).
      return {
        bg: family.pure ? "#f6f6f7" : hsl(h, t, 94), elevated: family.pure ? "#fbfbfc" : hsl(h, t, 97), panel: "#ffffff",
        panel2: hsl(h, t, 96.5), panel3: hsl(h, t, 92.5), border: hsl(h, Math.min(t, 24), 80), soft: hsl(h, Math.min(t, 24), 86),
        text: hsl(h, Math.min(30, t + 10), 12), muted: hsl(h, Math.min(12, t), 42), ...accents
      };
    }
    // Tinted light themes: every surface carries a soft wash of the family colour.
    const st = Math.min(70, 28 + t * 1.3);
    return {
      bg: hsl(h, st, 91), elevated: hsl(h, st, 94.5), panel: hsl(h, st, 97.5),
      panel2: hsl(h, st, 94.5), panel3: hsl(h, st, 90.5), border: hsl(h, st * 0.6, 76), soft: hsl(h, st * 0.6, 84),
      text: hsl(h, 38, 13), muted: hsl(h, 16, 38), ...accents
    };
  }
  return {
    bg: family.pure ? "#000000" : hsl(h, t, 6.5), elevated: family.pure ? "#060606" : hsl(h, t, 8.5),
    panel: family.pure ? "#0b0b0c" : hsl(h, t, 10.5), panel2: family.pure ? "#121214" : hsl(h, t, 13),
    panel3: family.pure ? "#1a1a1d" : hsl(h, t, 16.5), border: hsl(h, Math.min(t, 26), 27), soft: hsl(h, Math.min(t, 26), 21),
    text: hsl(h, Math.min(40, t + 15), 96), muted: hsl(h, Math.min(14, t), 68),
    accent: family.accent, accent2: family.accent2
  };
}

function parseUiTheme(value) {
  const [familyId, mode] = String(LEGACY_UI_THEMES[value] || value || "").split(":");
  const family = UI_THEMES.find(item => item.id === familyId) || UI_THEMES[0];
  return { family, mode: mode === "light" ? "light" : "dark" };
}

function currentUiThemeId() {
  try {
    const saved = localStorage.getItem(UI_THEME_KEY);
    if (saved) { const { family, mode } = parseUiTheme(saved.includes(":") || LEGACY_UI_THEMES[saved] ? saved : `${saved}:dark`); return `${family.id}:${mode}`; }
    return localStorage.getItem(THEME_KEY) === "light" ? "phrasync:light" : "phrasync:dark";
  } catch { return "phrasync:dark"; }
}

/** The theme on screen right now (which may be a Settings preview). */
function shownUiThemeId() {
  return document.documentElement.dataset.uiTheme || currentUiThemeId();
}

/** Readable text colour on top of an accent-filled button. */
function onAccentColor(color) {
  const probe = document.createElement("i");
  probe.style.color = color; document.body.append(probe);
  const [r, g, b] = getComputedStyle(probe).color.match(/[\d.]+/g).map(Number).map(value => value / 255);
  probe.remove();
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.45 ? "#15121a" : "#ffffff";
}

function applyUiTheme(id, remember = true) {
  const { family, mode } = parseUiTheme(id);
  const colors = themeColors(family, mode);
  const root = document.documentElement;
  root.dataset.theme = mode;
  root.dataset.uiTheme = `${family.id}:${mode}`;
  const vars = {
    "--bg": colors.bg, "--bg-elevated": colors.elevated, "--panel": colors.panel, "--panel-2": colors.panel2,
    "--panel-3": colors.panel3, "--border": colors.border, "--border-soft": colors.soft, "--text": colors.text,
    "--muted": colors.muted, "--muted-2": `color-mix(in srgb, ${colors.muted} 80%, ${colors.bg})`,
    "--accent": colors.accent, "--accent-2": colors.accent2, "--on-accent": onAccentColor(colors.accent),
    "--accent-soft": `color-mix(in srgb, ${colors.accent} ${mode === "light" ? 12 : 16}%, transparent)`
  };
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
  if (remember) {
    try { localStorage.setItem(UI_THEME_KEY, `${family.id}:${mode}`); localStorage.setItem(THEME_KEY, mode); } catch { /* storage blocked */ }
  }
  timeline?.refreshTheme?.();
  $$(".theme-grid").forEach(grid => renderThemeGrid(grid));
  $$("[data-theme-mode]").forEach(button => button.classList.toggle("active", button.dataset.themeMode === mode));
  const toggle = $("#modeToggle");
  if (toggle) { toggle.setAttribute("aria-checked", String(mode === "light")); toggle.title = mode === "light" ? "Light mode (click for dark)" : "Dark mode (click for light)"; }
}

/** Swatches for all 20 families, drawn in the mode currently on screen. */
function renderThemeGrid(grid) {
  const { family: active, mode } = parseUiTheme(shownUiThemeId());
  if (grid.dataset.mode === mode && grid.children.length) {
    $$(".theme-swatch", grid).forEach(swatch => swatch.classList.toggle("active", swatch.dataset.uiTheme === active.id));
    return;
  }
  grid.dataset.mode = mode;
  grid.replaceChildren(...UI_THEMES.map(family => {
    const c = themeColors(family, mode);
    const button = document.createElement("button");
    button.type = "button"; button.className = "theme-swatch"; button.dataset.uiTheme = family.id; button.title = family.name;
    button.classList.toggle("active", family.id === active.id);
    button.innerHTML = `<span class="theme-preview" style="background:${c.bg}">
        <i style="background:${c.panel};border-color:${c.soft}"></i>
        <i style="background:${c.panel2};border-color:${c.soft}"><b style="background:${c.accent}"></b><b style="background:${c.accent2}"></b></i>
      </span><span class="theme-name"></span>`;
    $(".theme-name", button).textContent = family.name;
    return button;
  }));
}

/** onPick gets the full "family:mode" id. */
function fillThemeGrid(grid, onPick) {
  renderThemeGrid(grid);
  grid.addEventListener("click", event => {
    const family = event.target.closest(".theme-swatch")?.dataset.uiTheme;
    if (family) onPick(`${family}:${parseUiTheme(shownUiThemeId()).mode}`);
  });
}

function modeSwitch(onPick) {
  const wrap = document.createElement("div");
  wrap.className = "theme-mode";
  wrap.innerHTML = '<button type="button" data-theme-mode="dark">☾ Dark</button><button type="button" data-theme-mode="light">☀ Light</button>';
  wrap.addEventListener("click", event => {
    const mode = event.target.closest("[data-theme-mode]")?.dataset.themeMode;
    if (mode) onPick(`${parseUiTheme(shownUiThemeId()).family.id}:${mode}`);
  });
  return wrap;
}

function closeThemePicker() { $("#themePicker").hidden = true; }

/** The quick picker under the palette button (or any other anchor). */
function openThemePicker(anchor) {
  const picker = $("#themePicker");
  if (!picker.hidden) return closeThemePicker();
  const box = anchor.getBoundingClientRect();
  picker.hidden = false;
  const width = picker.offsetWidth;
  picker.style.left = box.left < 300 ? `${box.right + 8}px` : `${Math.max(8, Math.min(innerWidth - width - 8, box.right - width))}px`;
  picker.style.top = `${Math.max(8, Math.min(innerHeight - picker.offsetHeight - 8, box.bottom + 8))}px`;
}

function initThemes() {
  const picker = document.createElement("div");
  picker.id = "themePicker"; picker.className = "theme-picker"; picker.hidden = true;
  picker.innerHTML = '<header><strong>Theme</strong><button type="button" data-theme-more>More settings</button></header><div class="theme-grid"></div>';
  document.body.append(picker);
  $("header strong", picker).after(modeSwitch(id => applyUiTheme(id)));
  fillThemeGrid($(".theme-grid", picker), id => applyUiTheme(id));
  $("[data-theme-more]", picker).addEventListener("click", () => {
    closeThemePicker();
    openSettings().then(() => showSettingsTab("general"));
  });

  const pickInSettings = id => { settingsThemePick = id; applyUiTheme(id, false); };
  $("#setThemeGrid").before(modeSwitch(pickInSettings));
  fillThemeGrid($("#setThemeGrid"), pickInSettings);

  // Sun/moon switch in the top bar, beside the palette button.
  const toggle = document.createElement("button");
  toggle.type = "button"; toggle.id = "modeToggle"; toggle.className = "mode-toggle";
  toggle.setAttribute("role", "switch"); toggle.setAttribute("aria-label", "Light mode");
  toggle.innerHTML = '<span class="mode-knob"></span><svg class="moon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 13.5A8 8 0 1 1 10.5 4a6.3 6.3 0 0 0 9.5 9.5z"/></svg><svg class="sun" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M18.7 5.3l-1.4 1.4M6.7 17.3l-1.4 1.4"/></svg>';
  toggle.addEventListener("click", () => {
    const { family, mode } = parseUiTheme(currentUiThemeId());
    applyUiTheme(`${family.id}:${mode === "light" ? "dark" : "light"}`);
  });
  $("#themeToggle").before(toggle);

  document.addEventListener("pointerdown", event => {
    if (!event.target.closest("#themePicker, #themeToggle, #homeTheme, .app-menu")) closeThemePicker();
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeThemePicker(); });
  $("#homeTheme").addEventListener("click", event => openThemePicker(event.currentTarget));
  applyUiTheme(currentUiThemeId());
}

initThemes();
