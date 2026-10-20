"use strict";

// The CapCut-style Menu in the top bar. Each item runs a command the editor
// already has; File's own items keep their ids so Ctrl+N/O/S still work.

const MENU_COMMANDS = {
  home: () => showHome(),
  export: () => $("#renderButton").click(),
  "add-line": () => els.addCueButton.click(),
  "delete-line": () => { if (selectedCueId) deleteCue(selectedCueId); else toast("Select a lyric line first."); },
  "undo-delete": () => restoreDeletedCue(),
  check: () => els.criticButton.click(),
  "toggle-left": () => setPanelVisible("left", $(".workspace").classList.contains("hide-left")),
  "toggle-right": () => setPanelVisible("right", $(".workspace").classList.contains("hide-right")),
  "reset-layout": () => resetLayout(),
  fullscreen: () => $("#fullscreenButton").click(),
  theme: () => openThemePicker($("#projectMenu summary")),
  language: () => openSettings().then(() => showSettingsTab("general")),
  diagnostics: () => $("#diagnosticsButton").click(),
  guide: () => $("#onboardingDialog")?.showModal(),
  about: () => openSettings().then(() => showSettingsTab("about")),
  settings: () => openSettings(),
  quit: () => $("#shutdownButton").click()
};

function initMenu() {
  const menu = $("#projectMenu");
  menu.addEventListener("toggle", () => {
    if (!menu.open) return;
    const workspace = $(".workspace");
    $('[data-menu="toggle-left"]', menu).classList.toggle("on", !workspace.classList.contains("hide-left"));
    $('[data-menu="toggle-right"]', menu).classList.toggle("on", !workspace.classList.contains("hide-right"));
  });
  menu.addEventListener("click", event => {
    const command = MENU_COMMANDS[event.target.closest("button[data-menu]")?.dataset.menu];
    if (command) Promise.resolve(command()).catch(error => toast(error.message, "error"));
  });
}

initMenu();
