"use strict";

// Draggable dividers either side of the preview, like CapCut: drag to make the
// Studio or lyric panel wider and the preview smaller (or the other way round).
// Double-click a divider to put that side back to its default width.

const LAYOUT_KEY = "karaokesesh.layout";
const PANEL_LIMITS = { left: [260, 640], right: [260, 620] };
const PREVIEW_MIN = 340;

let panelLayout = {};

function saveLayout() {
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(panelLayout)); } catch { /* storage blocked */ }
}

function applyLayout() {
  const workspace = $(".workspace");
  for (const side of ["left", "right"]) {
    const width = panelLayout[side];
    if (width) workspace.style.setProperty(`--${side}-w`, `${width}px`);
    else workspace.style.removeProperty(`--${side}-w`);
  }
  workspace.classList.toggle("hide-left", panelLayout.hideLeft === true);
  workspace.classList.toggle("hide-right", panelLayout.hideRight === true);
  timeline?.resize?.();
}

function setPanelVisible(side, visible) {
  panelLayout[side === "left" ? "hideLeft" : "hideRight"] = !visible;
  applyLayout(); saveLayout();
}

function resetLayout() {
  panelLayout = {};
  applyLayout(); saveLayout();
}

function initPanelSplitters() {
  const workspace = $(".workspace");
  const left = $(".controls-panel", workspace);
  const right = $(".timeline-panel", workspace);
  try { panelLayout = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") || {}; } catch { panelLayout = {}; }

  for (const side of ["left", "right"]) {
    const splitter = document.createElement("div");
    splitter.className = `panel-splitter ${side}`;
    splitter.setAttribute("role", "separator");
    splitter.setAttribute("aria-orientation", "vertical");
    splitter.title = "Drag to resize · double-click to reset";
    (side === "left" ? left : right)[side === "left" ? "after" : "before"](splitter);

    let drag = null;
    splitter.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      const panel = side === "left" ? left : right;
      const other = side === "left" ? right : left;
      const room = workspace.clientWidth - (other.offsetWidth || 0) - 60 - PREVIEW_MIN;
      drag = { x: event.clientX, width: panel.getBoundingClientRect().width, max: Math.min(PANEL_LIMITS[side][1], room) };
      splitter.setPointerCapture(event.pointerId);
      splitter.classList.add("dragging");
      document.body.classList.add("resizing-panels");
      event.preventDefault();
    });
    splitter.addEventListener("pointermove", event => {
      if (!drag) return;
      const delta = side === "left" ? event.clientX - drag.x : drag.x - event.clientX;
      const width = Math.round(Math.max(PANEL_LIMITS[side][0], Math.min(Math.max(PANEL_LIMITS[side][0], drag.max), drag.width + delta)));
      panelLayout[side] = width;
      applyLayout();
    });
    const end = () => {
      if (!drag) return;
      drag = null;
      splitter.classList.remove("dragging");
      document.body.classList.remove("resizing-panels");
      saveLayout();
      applyStageStyle?.();
    };
    splitter.addEventListener("pointerup", end);
    splitter.addEventListener("pointercancel", end);
    splitter.addEventListener("dblclick", () => {
      delete panelLayout[side];
      applyLayout(); saveLayout();
    });
  }
  applyLayout();
}

initPanelSplitters();
