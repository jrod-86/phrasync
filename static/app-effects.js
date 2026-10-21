"use strict";

// Effects tab and the Effects track on the timeline, laid out like CapCut:
// pick an effect, it drops onto the track at the playhead, then drag it,
// stretch its edges over the part of the song you want, and fine-tune it in
// Effects › Adjust. Clips live in project.effects; drawing is static/effects.js.

const EFFECT_TRACKS = 4;
const EFFECT_ROW = 30;
const EFFECT_LENGTH = 5;
let selectedEffectId = null;
let armedEffectId = null;
let effectDrag = null;
let effectsViewKey = "";
const SNAP_KEY = "phrasync.effectSnap";
let effectSnap = true;
try { effectSnap = localStorage.getItem(SNAP_KEY) !== "off"; } catch { /* storage blocked */ }

/** Edges an effect can snap to: song start and end, the playhead, other effects and footage clips. */
function effectSnapPoints(ignoreId) {
  const points = [0, projectDuration() + (project.timing.offset || 0), currentPlaybackTime()];
  for (const clip of effectList()) if (clip.id !== ignoreId) points.push(clip.start, clip.end);
  for (const clip of project.background.clips || []) points.push(clip.start, clip.end);
  return points;
}

/** The nearest snap point within 10 px of `value`, or null. Hold Alt to place freely. */
function snapTarget(value, points, event) {
  if (!effectSnap || event.altKey) return null;
  const tolerance = 10 / Math.max(1, $("#effectsLane").clientWidth) * timeline.viewSpan;
  let best = null;
  for (const point of points) if (Math.abs(point - value) <= tolerance && (best === null || Math.abs(point - value) < Math.abs(best - value))) best = point;
  return best;
}

function showSnapLine(time) {
  const lane = $("#effectsLane");
  let line = $(".effect-snap-line", lane);
  if (time === null) { line?.remove(); return; }
  if (!line) { line = document.createElement("b"); line.className = "effect-snap-line"; lane.append(line); }
  line.style.left = `${(time - (project.timing.offset || 0) - timeline.viewStart) / timeline.viewSpan * lane.clientWidth}px`;
}

function setEffectSnap(on) {
  effectSnap = on;
  try { localStorage.setItem(SNAP_KEY, on ? "on" : "off"); } catch { /* storage blocked */ }
  const button = $("#effectSnap");
  button.classList.toggle("on", on); button.setAttribute("aria-pressed", String(on));
}

const effectList = () => (project.effects ||= []);
const selectedEffect = () => effectList().find(clip => clip.id === selectedEffectId) || null;

function effectTrackCount() {
  return Math.min(EFFECT_TRACKS, Math.max(1, ...effectList().map(clip => (clip.track || 0) + 1)));
}

/** The first track with room for [start, end), so overlapping effects stack like CapCut. */
function freeEffectTrack(start, end, ignoreId) {
  for (let track = 0; track < EFFECT_TRACKS; track++) {
    if (!effectList().some(clip => clip.id !== ignoreId && (clip.track || 0) === track && clip.start < end && clip.end > start)) return track;
  }
  return 0;
}

function addEffect(type, start = currentPlaybackTime(), track = null) {
  if (!VFEffects.BY_ID[type]) return;
  start = Math.max(0, start);
  const end = start + EFFECT_LENGTH;
  const clip = { id: crypto.randomUUID(), type, start, end, track: track ?? freeEffectTrack(start, end), params: VFEffects.defaults(type) };
  effectList().push(clip);
  selectEffect(clip.id);
  effectsChanged();
}

function selectEffect(id, openAdjust = true) {
  selectedEffectId = id; armedEffectId = id;
  refreshEffectEditor();
  if (id && openAdjust) showSidebar("effects", "adjust");
  effectsViewKey = ""; renderEffectsLane();
}

function removeEffect(id = selectedEffectId) {
  project.effects = effectList().filter(clip => clip.id !== id);
  if (selectedEffectId === id) selectedEffectId = armedEffectId = null;
  refreshEffectEditor(); effectsChanged();
}

function effectsChanged() {
  effectsViewKey = ""; renderEffectsLane(); scheduleSave();
}

function refreshEffectEditor() {
  const clip = selectedEffect(), info = clip && VFEffects.BY_ID[clip.type];
  $("#effectEditor").hidden = !info;
  $("#effectEmpty").hidden = Boolean(info);
  if (!info) return;
  $("#effectName").textContent = t(info.name);
  const sliders = $("#effectSliders");
  sliders.replaceChildren(...info.params.map(([key, label]) => {
    const row = document.createElement("div"); row.className = "effect-slider";
    const name = document.createElement("span"); name.textContent = t(label);
    const range = document.createElement("input"); range.type = "range"; range.min = "0"; range.max = "100"; range.step = "1";
    const number = document.createElement("input"); number.type = "number"; number.min = "0"; number.max = "100"; number.step = "1";
    range.setAttribute("aria-label", t(label)); number.setAttribute("aria-label", t(label));
    range.value = number.value = String(Math.round(clip.params?.[key] ?? 50));
    const apply = raw => {
      const value = Math.max(0, Math.min(100, Math.round(Number(raw) || 0)));
      (clip.params ||= {})[key] = value; range.value = number.value = String(value);
      updateRangeUI?.(range); scheduleSave();
    };
    range.addEventListener("input", () => apply(range.value));
    number.addEventListener("change", () => apply(number.value));
    row.append(name, range, number);
    return row;
  }));
  $$("input[type=range]", sliders).forEach(range => updateRangeUI?.(range));
  $("#effectTiming").textContent = `${formatTime(clip.start)} → ${formatTime(clip.end)} · ${(clip.end - clip.start).toFixed(2)}s`;
}

function positionEffectBlock(element, clip) {
  const lane = $("#effectsLane"), offset = project.timing.offset || 0;
  element.style.left = `${(clip.start - offset - timeline.viewStart) / timeline.viewSpan * lane.clientWidth}px`;
  element.style.width = `${Math.max(6, (clip.end - clip.start) / timeline.viewSpan * lane.clientWidth)}px`;
  element.style.top = `${2 + (clip.track || 0) * EFFECT_ROW}px`;
}

function renderEffectsLane() {
  const lane = $("#effectsLane");
  if (!lane || !timeline || (effectDrag && !effectDrag.pan)) return;
  if (selectedEffectId && !selectedEffect()) { selectedEffectId = armedEffectId = null; refreshEffectEditor(); }
  const rows = effectTrackCount();
  lane.style.height = `${rows * EFFECT_ROW}px`;
  const dock = $("#timelineDock");
  const footageRows = project.background.tracks?.length || 1;
  dock.style.minHeight = `${326 + (footageRows - 1) * 38 + 50 + (rows - 1) * EFFECT_ROW}px`;
  const clips = effectList();
  const key = `${timeline.viewStart}:${timeline.viewSpan}:${lane.clientWidth}:${selectedEffectId}:${currentLanguage}:${JSON.stringify(clips.map(c => [c.id, c.type, c.start, c.end, c.track]))}`;
  if (key === effectsViewKey) return;
  effectsViewKey = key;
  lane.textContent = "";
  if (!clips.length) {
    const hint = document.createElement("span"); hint.className = "effects-lane-empty";
    hint.textContent = t("Add effects from the Effects tab");
    lane.append(hint); return;
  }
  const offset = project.timing.offset || 0;
  for (const clip of clips) {
    const info = VFEffects.BY_ID[clip.type];
    if (!info || clip.end - offset < timeline.viewStart || clip.start - offset > timeline.viewStart + timeline.viewSpan) continue;
    const block = document.createElement("div");
    block.className = `effect-block${clip.id === selectedEffectId ? " selected" : ""}`;
    block.dataset.id = clip.id;
    block.title = `${t(info.name)} · ${clip.start.toFixed(2)}–${clip.end.toFixed(2)}s`;
    const name = document.createElement("span"); name.textContent = `${info.icon} ${t(info.name)}`;
    const edges = ["start", "end"].map(edge => { const handle = document.createElement("i"); handle.dataset.edge = edge; handle.className = `footage-edge ${edge}`; return handle; });
    block.append(...edges, name);
    positionEffectBlock(block, clip);
    lane.append(block);
  }
}

function buildEffectLibrary() {
  const grid = $("#effectGrid");
  for (const info of VFEffects.CATALOG) {
    const card = document.createElement("button");
    card.type = "button"; card.className = `effect-card fx-${info.id}`; card.dataset.effect = info.id; card.draggable = true;
    card.innerHTML = '<span class="effect-swatch"></span><strong></strong>';
    $(".effect-swatch", card).textContent = info.icon;
    $("strong", card).textContent = t(info.name);
    card.addEventListener("click", () => addEffect(info.id));
    card.addEventListener("dragstart", event => {
      event.dataTransfer.setData("application/x-phrasync-effect", info.id);
      event.dataTransfer.effectAllowed = "copy";
    });
    grid.append(card);
  }
}

function laneTrackAt(lane, clientY) {
  return Math.max(0, Math.min(EFFECT_TRACKS - 1, Math.floor((clientY - lane.getBoundingClientRect().top) / EFFECT_ROW)));
}

function initEffects() {
  buildEffectLibrary();
  const lane = $("#effectsLane");
  lane.addEventListener("pointerdown", event => {
    if (event.button === 1) {
      event.preventDefault(); lane.setPointerCapture(event.pointerId);
      effectDrag = { pan: true, x: event.clientX, viewStart: timeline.viewStart }; timeline.follow = false; return;
    }
    if (event.button !== 0) return;
    const block = event.target.closest(".effect-block");
    if (!block) {
      armedEffectId = null;
      seekTo(timeline.xToTime(event.clientX - lane.getBoundingClientRect().left) + (project.timing.offset || 0));
      return;
    }
    selectEffect(block.dataset.id);
    lane.setPointerCapture(event.pointerId);
    effectDrag = { id: block.dataset.id, x: event.clientX, original: clone(selectedEffect()), mode: event.target.dataset.edge || "move" };
  });
  lane.addEventListener("pointermove", event => {
    if (!effectDrag) return;
    const delta = (event.clientX - effectDrag.x) / Math.max(1, lane.clientWidth) * timeline.viewSpan;
    if (effectDrag.pan) { timeline.setView(effectDrag.viewStart - delta, timeline.viewSpan); return; }
    const clip = selectedEffect(), original = effectDrag.original;
    if (!clip) return;
    const points = effectDrag.points ||= effectSnapPoints(clip.id);
    let snapped = null;
    if (effectDrag.mode === "move") {
      const length = original.end - original.start;
      let start = Math.max(0, original.start + delta);
      const head = snapTarget(start, points, event), tail = snapTarget(start + length, points, event);
      if (head !== null && (tail === null || Math.abs(head - start) <= Math.abs(tail - start - length))) { start = head; snapped = head; }
      else if (tail !== null) { start = Math.max(0, tail - length); snapped = tail; }
      clip.start = start; clip.end = start + length;
      clip.track = laneTrackAt(lane, event.clientY);
      if (clip.track >= effectTrackCount()) lane.style.height = `${(clip.track + 1) * EFFECT_ROW}px`;
    } else if (effectDrag.mode === "start") {
      let start = Math.max(0, Math.min(original.start + delta, original.end - 0.1));
      const target = snapTarget(start, points, event);
      if (target !== null && target < original.end - 0.1) { start = target; snapped = target; }
      clip.start = start;
    } else {
      let end = Math.max(clip.start + 0.1, original.end + delta);
      const target = snapTarget(end, points, event);
      if (target !== null && target > clip.start + 0.1) { end = target; snapped = target; }
      clip.end = end;
    }
    showSnapLine(snapped);
    const element = lane.querySelector(`[data-id="${clip.id}"]`);
    if (element) positionEffectBlock(element, clip);
    $("#effectTiming").textContent = `${formatTime(clip.start)} → ${formatTime(clip.end)} · ${(clip.end - clip.start).toFixed(2)}s`;
  });
  const release = () => { if (!effectDrag) return; effectDrag = null; showSnapLine(null); refreshEffectEditor(); effectsChanged(); };
  lane.addEventListener("pointerup", release); lane.addEventListener("pointercancel", release); lane.addEventListener("lostpointercapture", release);
  lane.addEventListener("auxclick", event => { if (event.button === 1) event.preventDefault(); });
  lane.addEventListener("wheel", event => {
    event.preventDefault(); timeline.follow = false;
    if (event.ctrlKey) timeline.zoomAt(event.deltaY > 0 ? 1.18 : .85, event.clientX - lane.getBoundingClientRect().left);
    else timeline.setView(timeline.viewStart + (event.deltaX || event.deltaY) / 400 * timeline.viewSpan, timeline.viewSpan);
  }, { passive: false });
  // Drag an effect card from the Effects tab straight onto the track.
  const carriesEffect = event => [...(event.dataTransfer?.types || [])].includes("application/x-phrasync-effect");
  lane.addEventListener("dragover", event => { if (!carriesEffect(event)) return; event.preventDefault(); lane.classList.add("drop-active"); });
  lane.addEventListener("dragleave", () => lane.classList.remove("drop-active"));
  lane.addEventListener("drop", event => {
    if (!carriesEffect(event)) return;
    event.preventDefault(); lane.classList.remove("drop-active");
    const start = timeline.xToTime(event.clientX - lane.getBoundingClientRect().left) + (project.timing.offset || 0);
    const track = laneTrackAt(lane, event.clientY);
    const busy = effectList().some(clip => (clip.track || 0) === track && clip.start < start + EFFECT_LENGTH && clip.end > start);
    addEffect(event.dataTransfer.getData("application/x-phrasync-effect"), start, busy ? null : track);
  });
  // Delete removes the effect you just clicked; clicking anywhere else disarms it.
  document.addEventListener("pointerdown", event => {
    if (!event.target.closest?.("#effectsLane, #effectDetails")) armedEffectId = null;
  }, true);
  document.addEventListener("keydown", event => {
    if (!armedEffectId || !["Delete", "Backspace"].includes(event.key)) return;
    if (event.target.closest?.("input, textarea, select, [contenteditable=true]") || document.querySelector("dialog[open]")) return;
    event.preventDefault(); event.stopImmediatePropagation();
    removeEffect(armedEffectId);
  }, true);
  $("#effectRemove").addEventListener("click", () => removeEffect());
  $("#effectSnap").addEventListener("click", () => setEffectSnap(!effectSnap));
  setEffectSnap(effectSnap);
  $("#effectDuplicate").addEventListener("click", () => {
    const clip = selectedEffect(); if (!clip) return;
    const copy = { ...clone(clip), id: crypto.randomUUID(), start: clip.end, end: clip.end + clip.end - clip.start };
    copy.track = freeEffectTrack(copy.start, copy.end);
    effectList().push(copy); selectEffect(copy.id); effectsChanged();
  });
  $("#effectReset").addEventListener("click", () => {
    const clip = selectedEffect(); if (!clip) return;
    clip.params = VFEffects.defaults(clip.type); refreshEffectEditor(); scheduleSave();
  });
  document.addEventListener("phrasync-language-change", () => {
    $$("#effectGrid .effect-card").forEach(card => { $("strong", card).textContent = t(VFEffects.BY_ID[card.dataset.effect].name); });
    refreshEffectEditor(); effectsViewKey = ""; renderEffectsLane();
  });
  refreshEffectEditor();
}

window.renderEffectsLane = renderEffectsLane;
initEffects();
