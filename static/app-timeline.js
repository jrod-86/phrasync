"use strict";

/* ------------------------------------------------------------------ *
 * Audio analysis, alignment and the timeline dock
 * ------------------------------------------------------------------ */

async function ensureAnalysis(force = false) {
  if (!project.audioAssetId) {
    toast(project.mode === "subtitles" ? "Load a video or audio file first." : "Load a song first.", "error");
    return null;
  }
  if (analysis && !force) return analysis;
  if (analysisPending) return null;
  analysisPending = true;
  const label = els.analyzeButton.textContent;
  els.analyzeButton.disabled = true;
  els.analyzeButton.textContent = "Analyzing…";
  try {
    analysis = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId: project.sourceAssetId || project.audioAssetId, refresh: force })
    });
    project.timing.bpm = analysis.bpm || 0;
    project.timing.beatOffset = analysis.beatOffset || 0;
    project.background.effectOnsets = analysis.percussiveOnsets?.length ? analysis.percussiveOnsets : analysis.onsets || [];
    updateSyncSummary();
    timeline?.draw();
    scheduleSave();
    return analysis;
  } catch (error) {
    toast(`Analysis failed: ${error.message}`, "error");
    return null;
  } finally {
    analysisPending = false;
    els.analyzeButton.disabled = false;
    els.analyzeButton.textContent = label;
  }
}
function updateSyncSummary(stats = null) {
  if (!analysis) {
    els.syncSummary.className = "sync-summary";
    els.syncSummary.innerHTML = "<b>—</b><span>No audio analysis</span>";
    els.timelineMeta.textContent = project.audio?.name || "no audio";
    return;
  }
  const bpm = analysis.bpm ? `${analysis.bpm.toFixed(1)} BPM` : "BPM unavailable";
  els.timelineMeta.textContent =
    `${bpm} · ${(analysis.onsets || []).length} onsets · ${formatTime(analysis.duration)}`;

  if (stats) {
    const grade = stats.score >= 78 ? "good" : stats.score >= 55 ? "warn" : "bad";
    els.syncSummary.className = `sync-summary ${grade}`;
    els.syncSummary.innerHTML =
      `<b>${stats.score}/100</b><span>mean offset ${Math.round(stats.meanError * 1000)} ms · ` +
      `${Math.round(stats.tight * 100)}% of words within 60 ms</span>`;
  } else {
    els.syncSummary.className = "sync-summary";
    els.syncSummary.innerHTML = `<b>${bpm}</b><span>${(analysis.onsets || []).length} vocal onsets detected</span>`;
  }
}
/**
 * Align whatever cues the project currently holds against the song.
 *
 * `auto` is used by the import paths, which run this without being asked: any
 * route that produces cues should land on the beat, not just the transcriber.
 * It stays quiet when there is no audio to align to.
 */
async function runAutoAlign(options = {}) {
  const auto = Boolean(options.auto);
  if (!project.cues.length) {
    if (auto) return null;
    return toast("There are no phrases to align.", "error");
  }
  if (auto && !project.audioAssetId) return null;
  const data = await ensureAnalysis();
  if (!data) return null;
  const label = els.autoAlignButton.textContent;
  els.autoAlignButton.disabled = true;
  els.autoAlignButton.textContent = "Aligning…";
  try {
    const result = await api("/api/align", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cues: project.cues,
        analysis: data,
        options: {
          snapWords: true,
          wordWindow: Number(els.snapWindow.value),
          wordStrength: Number(els.snapStrength.value),
          snapPhrases: els.snapPhrasesToggle.checked,
          autoOffset: true
        }
      })
    });
    project.cues = result.cues;
    selectedCueId = project.cues.find(cue => cue.id === selectedCueId)?.id || project.cues[0]?.id || null;
    renderCueList(); updateDurationUI(); restartLyricAnimation(); scheduleSave();
    timeline?.draw();
    updateSyncSummary(result.stats);
    const shift = Math.round((result.report.offset || 0) * 1000);
    toast(
      `Aligned ${result.report.words} words · latency ${shift > 0 ? "+" : ""}${shift} ms · ` +
      `offset ${Math.round(result.stats.meanError * 1000)} ms`,
      result.stats.score >= 60 ? "success" : ""
    );
  } catch (error) {
    toast(`Alignment failed: ${error.message}`, "error");
  } finally {
    els.autoAlignButton.disabled = false;
    els.autoAlignButton.textContent = label;
  }
}

function selectedCue() {
  return project.cues.find(cue => cue.id === selectedCueId) || null;
}

function materialiseWords(cue) {
  if (!cue) return [];
  const words = window.VFKinetic.cueWords(cue);
  cue.words = words.map(word => ({ text: word.text, start: word.start, end: word.end }));
  return cue.words;
}

function updateWordLabel() {
  const cue = selectedCue();
  if (!cue) {
    els.selectedWordLabel.textContent = "no phrase selected";
    return;
  }
  const words = window.VFKinetic.cueWords(cue);
  if (!words.length) {
    els.selectedWordLabel.textContent = "phrase has no words";
    return;
  }
  selectedWordIndex = Math.min(selectedWordIndex, words.length - 1);
  const word = words[selectedWordIndex];
  const derived = !(Array.isArray(cue.words) && cue.words.length === words.length);
  els.selectedWordLabel.textContent =
    `“${word.text}” ${word.start.toFixed(2)}s${derived ? " (estimated)" : ""} · ${selectedWordIndex + 1}/${words.length}`;
}

function nudgeWord(delta) {
  const cue = selectedCue();
  if (!cue) return toast("Select a phrase first.", "error");
  const words = materialiseWords(cue);
  if (!words.length) return;
  const index = Math.min(selectedWordIndex, words.length - 1);
  const word = words[index];
  word.start = Math.max(0, word.start + delta);
  word.end = Math.max(word.start + 0.06, word.end + delta);
  const previous = words[index - 1];
  const next = words[index + 1];
  if (previous && previous.end > word.start) previous.end = Math.max(previous.start + 0.06, word.start);
  if (next && next.start < word.end) next.start = word.end;
  cue.start = Math.min(cue.start, words[0].start);
  cue.end = Math.max(cue.end, words[words.length - 1].end);
  updateWordLabel(); restartLyricAnimation(); timeline?.draw(); scheduleSave();
}

function selectWordAtPlayhead() {
  const cue = selectedCue();
  if (!cue) return;
  const words = window.VFKinetic.cueWords(cue);
  if (!words.length) return;
  const time = lyricTime();
  let index = words.findIndex(word => time >= word.start && time < word.end);
  if (index < 0) {
    index = words.reduce(
      (best, word, i) => (Math.abs(word.start - time) < Math.abs(words[best].start - time) ? i : best),
      0
    );
  }
  selectedWordIndex = Math.max(0, index);
  updateWordLabel();
}

/** Tap sync: each press of T stamps the next word start at the playhead. */
function handleTap() {
  const cue = selectedCue();
  if (!cue) return toast("Select a phrase to sync.", "error");
  const words = materialiseWords(cue);
  if (!words.length) return;
  if (!tapQueue.length) tapQueue = words.map((_, index) => index);
  const index = tapQueue.shift();
  const time = lyricTime();
  words[index].start = time;
  if (index > 0) words[index - 1].end = Math.max(words[index - 1].start + 0.06, time);
  words[index].end = Math.max(time + 0.12, words[index].end);
  for (let i = index + 1; i < words.length; i += 1) {
    words[i].start = Math.max(words[i].start, words[i - 1].end);
    words[i].end = Math.max(words[i].start + 0.08, words[i].end);
  }
  cue.start = Math.min(cue.start, words[0].start);
  cue.end = Math.max(cue.end, words[words.length - 1].end);
  selectedWordIndex = Math.min(index + 1, words.length - 1);
  if (!tapQueue.length) {
    tapArmed = false;
    els.tapSyncButton.classList.remove("armed");
    toast("Tap sync completed for this phrase.", "success");
    scheduleSave();
  }
  updateWordLabel(); timeline?.draw(); restartLyricAnimation();
}

function toggleTapSync() {
  tapArmed = !tapArmed;
  tapQueue = [];
  els.tapSyncButton.classList.toggle("armed", tapArmed);
  if (tapArmed) toast("Tap sync is active: press T on every word while the song plays.");
}

function splitCueAtPlayhead() {
  const cue = selectedCue();
  const time = lyricTime();
  if (!cue || time <= cue.start + 0.1 || time >= cue.end - 0.1) {
    return toast("Move the playhead inside the selected phrase.", "error");
  }
  const words = window.VFKinetic.cueWords(cue);
  const head = words.filter(word => word.start < time);
  const tail = words.filter(word => word.start >= time);
  if (!head.length || !tail.length) return toast("Invalid split point.", "error");

  const strip = list => list.map(word => ({ text: word.text, start: word.start, end: word.end }));
  const second = {
    id: `cue-${Date.now()}`,
    start: tail[0].start,
    end: cue.end,
    text: tail.map(word => word.text).join(" "),
    words: strip(tail)
  };
  cue.end = head[head.length - 1].end;
  cue.text = head.map(word => word.text).join(" ");
  cue.words = strip(head);
  project.cues.splice(project.cues.indexOf(cue) + 1, 0, second);
  selectedCueId = second.id;
  renderCueList(); updateDurationUI(); timeline?.draw(); scheduleSave();
  toast("Phrase split.", "success");
}

function resetCueWords() {
  const cue = selectedCue();
  if (!cue) return;
  cue.words = [];
  selectedWordIndex = 0;
  updateWordLabel(); restartLyricAnimation(); timeline?.draw(); scheduleSave();
  toast("Word timing recalculated from the phrase duration.");
}

function timelineState() {
  return {
    cues: project.cues,
    selectedCueId,
    duration: projectDuration(),
    exportRange: project.exportRange,
    exportOffset: project.timing.offset || 0,
    analysis,
    audioLoaded: Boolean(project.audioAssetId),
    snap: project.timing.snapMode !== "off",
    snapOnsets: project.timing.snapMode === "onset",
    snapBeats: project.timing.snapMode === "beat"
  };
}

function setupTimeline() {
  setupExportRange();
  const scrollbar = document.getElementById("timelineScroll");
  const track = document.getElementById("timelineScrollTrack");
  let expectedScroll = 0;
  const syncScroll = (start, span) => {
    if (!timeline) return;
    const width = scrollbar.clientWidth;
    const max = Math.max(0, timeline.duration() - span * .25, start);
    const size = `${width * (1 + max / span)}px`;
    if (track.style.width !== size) track.style.width = size;
    expectedScroll = Math.max(0, start) / span * width;
    if (Math.abs(scrollbar.scrollLeft - expectedScroll) > 1) scrollbar.scrollLeft = expectedScroll;
    els.followToggle.classList.toggle("off", !timeline.follow);
    renderFootageLane();
  };
  timeline = window.VFTimeline.create({
    canvas: els.timelineCanvas,
    host: els.timelineWrap,
    getState: timelineState,
    getTime: () => lyricTime(),
    onView: syncScroll,
    onSeek: time => {
      timeline.follow = false;
      els.followToggle.classList.add("off");
      seekTo(time + (project.timing.offset || 0));
    },
    onSelect: id => {
      selectedCueId = id;
      revealCueInList(id);
      selectedWordIndex = 0;
      tapQueue = [];
      $$(".cue-card", els.cueList).forEach(card => card.classList.toggle("selected", card.dataset.id === id));
      updateWordLabel();
    },
    onChange: kind => {
      if (kind === "live") {
        restartLyricAnimation();
        updateWordLabel();
        return;
      }
      normalizeCues();
      renderCueList();
      updateDurationUI();
      restartLyricAnimation();
      updateWordLabel();
      scheduleSave();
    }
  });
  timeline.fitAll();
  // Click a lyric block on the timeline, then Delete or Backspace removes it.
  // The key only acts while the last click was on a block, so typing or
  // pressing Delete anywhere else never removes a line.
  let armedCueId = null;
  document.addEventListener("pointerdown", event => {
    if (event.target !== timeline.canvas) { armedCueId = null; return; }
    const { x, y } = timeline.localPoint(event);
    const hit = timeline.hitTest(x, y);
    armedCueId = hit?.type === "phrase" ? hit.cue.id : null;
  }, true);
  document.addEventListener("keydown", event => {
    if (event.target.matches("input,textarea,select") || document.querySelector("dialog[open]")) return;
    if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === "z") {
      if (restoreDeletedCue()) event.preventDefault();
      return;
    }
    if ((event.key === "Delete" || event.key === "Backspace") && armedCueId && armedCueId === selectedCueId) {
      event.preventDefault();
      deleteCue(armedCueId);
      armedCueId = null;
    }
  });
  scrollbar.addEventListener("scroll", () => {
    if (Math.abs(scrollbar.scrollLeft - expectedScroll) < 2) return;
    timeline.follow = false;
    timeline.setView(scrollbar.scrollLeft / Math.max(1, scrollbar.clientWidth) * timeline.viewSpan, timeline.viewSpan);
  });

  const zoomPlayhead = factor => {
    const time = currentPlaybackTime() - (project.timing.offset || 0);
    const span = Math.max(.6, Math.min(timeline.duration() + 2, timeline.viewSpan * factor));
    timeline.follow = false;
    timeline.setView(time - span / 2, span);
  };
  els.zoomInButton.addEventListener("click", () => zoomPlayhead(.6));
  els.zoomOutButton.addEventListener("click", () => zoomPlayhead(1.7));
  els.zoomFitButton.addEventListener("click", () => timeline.fitAll());
  els.followToggle.addEventListener("click", () => {
    timeline.follow = !timeline.follow;
    els.followToggle.classList.toggle("off", !timeline.follow);
  });
  $$("button", els.snapMode).forEach(button => button.addEventListener("click", () => {
    project.timing.snapMode = button.dataset.value;
    $$("button", els.snapMode).forEach(item => item.classList.toggle("active", item === button));
    timeline.draw(); scheduleSave();
  }));

  let dockDrag = null;
  els.dockGrip.addEventListener("pointerdown", event => {
    els.dockGrip.setPointerCapture(event.pointerId);
    dockDrag = { y: event.clientY, height: els.timelineDock.getBoundingClientRect().height };
  });
  els.dockGrip.addEventListener("pointermove", event => {
    if (!dockDrag) return;
    const height = Math.max(326, Math.min(480, dockDrag.height + (dockDrag.y - event.clientY)));
    els.timelineDock.style.setProperty("--dock-height", `${height}px`);
    timeline.resize();
  });
  els.dockGrip.addEventListener("pointerup", () => {
    dockDrag = null;
    applyStageStyle();
  });
}
