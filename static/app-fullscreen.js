"use strict";

// Full-screen preview keeps its playback controls: the transport bar moves
// into the stage while it is full screen, fades out when the mouse rests and
// comes back on any movement, then returns under the preview on exit.

const FULLSCREEN_IDLE_MS = 2500;
let fullscreenIdleTimer = null;

function wakeFullscreenControls() {
  els.stage.classList.remove("controls-idle");
  clearTimeout(fullscreenIdleTimer);
  fullscreenIdleTimer = setTimeout(() => {
    const transport = $(".transport");
    if (!transport?.matches(":hover") && !exitFullscreenButton.matches(":hover")) els.stage.classList.add("controls-idle");
  }, FULLSCREEN_IDLE_MS);
}

// Floating exit button, shown only while the preview is full screen.
const exitFullscreenButton = Object.assign(document.createElement("button"), {
  type: "button", className: "exit-fullscreen", title: "Exit full screen (Esc)",
  innerHTML: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg>'
});
exitFullscreenButton.setAttribute("aria-label", "Exit full screen");
exitFullscreenButton.addEventListener("click", () => document.exitFullscreen?.());

document.addEventListener("fullscreenchange", () => {
  const transport = $(".transport");
  if (!transport) return;
  const full = document.fullscreenElement === els.stage;
  if (full) {
    els.stage.append(transport, exitFullscreenButton);
    wakeFullscreenControls();
  } else if (transport.parentElement === els.stage) {
    $("#stageShell").after(transport);
    exitFullscreenButton.remove();
    clearTimeout(fullscreenIdleTimer);
    els.stage.classList.remove("controls-idle");
  }
  transport.classList.toggle("fullscreen-transport", full);
});

["mousemove", "pointerdown", "keydown"].forEach(type =>
  els.stage.addEventListener(type, () => {
    if (document.fullscreenElement === els.stage) wakeFullscreenControls();
  }));
document.addEventListener("keydown", () => {
  if (document.fullscreenElement === els.stage) wakeFullscreenControls();
});

// Click the picture to play or pause; double-click to enter or leave full
// screen. The single click waits a moment so a double-click never also
// toggles playback. Clicks on the controls themselves are left alone.
const STAGE_CLICK_DELAY_MS = 250;
let stageClickTimer = null;

function stageControlClick(event) {
  return Boolean(event.target.closest("button, input, select, textarea, a, label, .transport"));
}

els.stage.addEventListener("click", event => {
  if (event.button !== 0 || stageControlClick(event)) return;
  clearTimeout(stageClickTimer);
  if (event.detail > 1) return;
  stageClickTimer = setTimeout(() => togglePlay(), STAGE_CLICK_DELAY_MS);
});

els.stage.addEventListener("dblclick", event => {
  if (stageControlClick(event)) return;
  clearTimeout(stageClickTimer);
  event.preventDefault();
  if (document.fullscreenElement === els.stage) document.exitFullscreen?.();
  else els.stage.requestFullscreen?.();
});
