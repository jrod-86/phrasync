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
    if (!transport?.matches(":hover")) els.stage.classList.add("controls-idle");
  }, FULLSCREEN_IDLE_MS);
}

document.addEventListener("fullscreenchange", () => {
  const transport = $(".transport");
  if (!transport) return;
  const full = document.fullscreenElement === els.stage;
  if (full) {
    els.stage.append(transport);
    wakeFullscreenControls();
  } else if (transport.parentElement === els.stage) {
    $("#stageShell").after(transport);
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
