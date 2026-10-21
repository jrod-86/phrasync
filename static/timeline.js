/*
 * KaraokeSesh timeline — waveform, onset/beat grid, draggable phrase and word
 * lanes. Canvas based so a four-minute song with a thousand words still pans
 * and zooms at 60fps.
 */
(() => {
  "use strict";

  const LANES = { ruler: 20, wave: 62, phrase: 30, word: 34, gap: 6 };
  const EDGE_GRAB = 7;
  const MIN_WORD = 0.06;
  const MIN_CUE = 0.15;

  const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

  function readTheme(element) {
    const style = getComputedStyle(element);
    const get = (name, fallback) => (style.getPropertyValue(name) || "").trim() || fallback;
    return {
      text: get("--text", "#f4f1f8"),
      muted: get("--muted", "#9693a5"),
      muted2: get("--muted-2", "#6e6b7c"),
      border: get("--border", "#28283a"),
      borderSoft: get("--border-soft", "#20202f"),
      panel: get("--panel", "#12121b"),
      panel2: get("--panel-2", "#171722"),
      panel3: get("--panel-3", "#1d1d2a"),
      accent: get("--accent", "#dc62ff"),
      accent2: get("--accent-2", "#8d5cff"),
      success: get("--success", "#65e4b1"),
      warning: get("--warning", "#ffc66d"),
      danger: get("--danger", "#ff7188"),
      font: get("--ui-font", "Inter, sans-serif")
    };
  }

  function formatTick(seconds) {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${(s < 10 ? "0" : "")}${s.toFixed(s % 1 ? 1 : 0)}`;
  }

  class Timeline {
    constructor(options) {
      this.canvas = options.canvas;
      this.ctx = this.canvas.getContext("2d");
      this.host = options.host || this.canvas.parentElement;
      this.getState = options.getState;
      this.onChange = options.onChange || (() => {});
      this.onSeek = options.onSeek || (() => {});
      this.onSelect = options.onSelect || (() => {});
      this.onView = options.onView || (() => {});
      this.getTime = options.getTime || (() => 0);

      this.viewStart = 0;
      this.viewSpan = 12;
      this.dpr = 1;
      this.width = 0;
      this.height = 0;
      this.drag = null;
      this.hover = null;
      this.follow = true;
      this.theme = readTheme(document.documentElement);
      this.waveCache = { key: "", canvas: null };

      this.bind();
      this.resize();
    }

    /* --------------------------- geometry --------------------------- */

    get laneTops() {
      const ruler = 0;
      const wave = LANES.ruler;
      const phrase = wave + LANES.wave + LANES.gap;
      const word = phrase + LANES.phrase + 4;
      return { ruler, wave, phrase, word, bottom: word + LANES.word };
    }

    timeToX(time) {
      return ((time - this.viewStart) / this.viewSpan) * this.width;
    }

    xToTime(x) {
      return this.viewStart + (x / this.width) * this.viewSpan;
    }

    duration() {
      return Math.max(1, this.getState().duration || 1);
    }

    /** Widest zoom-out: the whole song shrinks to a tenth of the track, like CapCut. */
    maxSpan() {
      return Math.max(60, this.duration() * 10);
    }

    setView(start, span) {
      const duration = this.duration();
      this.viewSpan = clamp(span, 0.6, this.maxSpan());
      this.viewStart = clamp(start, -0.4, Math.max(0, duration - this.viewSpan * 0.25));
      this.onView(this.viewStart, this.viewSpan);
      this.draw();
    }

    zoomAt(factor, pivotX) {
      const pivotTime = this.xToTime(pivotX);
      const span = clamp(this.viewSpan * factor, 0.6, this.maxSpan());
      const ratio = pivotX / Math.max(1, this.width);
      this.setView(pivotTime - span * ratio, span);
    }

    fitAll() {
      this.setView(0, this.duration());
    }

    focusTime(time, keepSpan = true) {
      const span = keepSpan ? this.viewSpan : 8;
      this.setView(time - span / 2, span);
    }

    /* ----------------------------- data ----------------------------- */

    snapTargets(excludeCueId) {
      const state = this.getState();
      if (!state.snap) return [];
      const targets = [];
      const analysis = state.analysis;
      const from = this.viewStart - 1;
      const to = this.viewStart + this.viewSpan + 1;
      if (analysis) {
        if (state.snapOnsets !== false) {
          for (const value of analysis.onsets || []) if (value >= from && value <= to) targets.push(value);
        }
        if (state.snapBeats && analysis.bpm > 0) {
          const period = 60 / analysis.bpm;
          const first = Math.ceil((from - analysis.beatOffset) / period);
          const last = Math.floor((to - analysis.beatOffset) / period);
          for (let i = first; i <= last; i += 1) targets.push(analysis.beatOffset + i * period);
        }
      }
      for (const cue of state.cues) {
        if (cue.id === excludeCueId) continue;
        targets.push(cue.start, cue.end);
      }
      return targets;
    }

    applySnap(time, excludeCueId) {
      if (this.drag && this.drag.noSnap) return time;
      const targets = this.snapTargets(excludeCueId);
      if (!targets.length) return time;
      // Snap tolerance is expressed in pixels so it stays usable at every zoom.
      const window = (10 / Math.max(1, this.width)) * this.viewSpan;
      let best = time;
      let bestDistance = window;
      for (const target of targets) {
        const distance = Math.abs(target - time);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = target;
        }
      }
      return best;
    }

    wordsOf(cue) {
      return window.VFKinetic.cueWords(cue).map(word => ({ ...word }));
    }

    /* ---------------------------- hit test -------------------------- */

    hitTest(x, y) {
      const state = this.getState();
      const tops = this.laneTops;

      if (y >= tops.word && y <= tops.word + LANES.word) {
        const cue = state.cues.find(item => item.id === state.selectedCueId);
        if (cue) {
          const words = this.wordsOf(cue);
          for (let index = words.length - 1; index >= 0; index -= 1) {
            const word = words[index];
            const x1 = this.timeToX(word.start);
            const x2 = this.timeToX(word.end);
            if (x >= x1 - EDGE_GRAB && x <= x2 + EDGE_GRAB) {
              const mode = x <= x1 + EDGE_GRAB ? "start" : x >= x2 - EDGE_GRAB ? "end" : "move";
              return { type: "word", cue, wordIndex: index, mode, words };
            }
          }
        }
        return null;
      }

      if (y >= tops.phrase && y <= tops.phrase + LANES.phrase) {
        for (let index = state.cues.length - 1; index >= 0; index -= 1) {
          const cue = state.cues[index];
          const x1 = this.timeToX(cue.start);
          const x2 = this.timeToX(cue.end);
          if (x >= x1 - EDGE_GRAB && x <= x2 + EDGE_GRAB) {
            const mode = x <= x1 + EDGE_GRAB ? "start" : x >= x2 - EDGE_GRAB ? "end" : "move";
            return { type: "phrase", cue, mode };
          }
        }
        return null;
      }

      return { type: "scrub" };
    }

    /* ----------------------------- events --------------------------- */

    bind() {
      const canvas = this.canvas;

      canvas.addEventListener("pointerdown", event => {
        if (event.button !== 0 && event.button !== 1) return;
        canvas.setPointerCapture(event.pointerId);
        const { x, y } = this.localPoint(event);
        if (event.button === 1) {
          event.preventDefault(); this.follow = false;
          this.drag = { type: "pan", originX: x, originStart: this.viewStart };
          canvas.style.cursor = "grabbing";
          this.onView(this.viewStart, this.viewSpan); return;
        }
        const hit = this.hitTest(x, y);
        if (!hit) return;

        if (hit.type === "scrub") {
          this.follow = false;
          this.drag = { type: "scrub" };
          this.onSeek(clamp(this.xToTime(x), 0, this.duration()));
          return;
        }

        const state = this.getState();
        if (hit.cue && hit.cue.id !== state.selectedCueId) this.onSelect(hit.cue.id);

        if (hit.type === "phrase") {
          this.drag = {
            type: "phrase",
            mode: hit.mode,
            cue: hit.cue,
            startTime: this.xToTime(x),
            originStart: hit.cue.start,
            originEnd: hit.cue.end,
            originWords: this.wordsOf(hit.cue),
            ripple: event.shiftKey,
            rippleCues: event.shiftKey
              ? state.cues.filter(item => item.start >= hit.cue.end - 1e-6).map(item => ({
                  cue: item, start: item.start, end: item.end, words: this.wordsOf(item)
                }))
              : [],
            noSnap: event.altKey
          };
        } else if (hit.type === "word") {
          const word = hit.words[hit.wordIndex];
          this.drag = {
            type: "word",
            mode: hit.mode,
            cue: hit.cue,
            wordIndex: hit.wordIndex,
            words: hit.words,
            startTime: this.xToTime(x),
            originStart: word.start,
            originEnd: word.end,
            ripple: event.shiftKey,
            noSnap: event.altKey
          };
          // Materialise derived word timings so the edit has something to store.
          hit.cue.words = hit.words.map(item => ({ text: item.text, start: item.start, end: item.end }));
        }
        this.draw();
      });

      canvas.addEventListener("pointermove", event => {
        const { x, y } = this.localPoint(event);
        if (this.drag) {
          this.updateDrag(x, event);
          return;
        }
        const hit = this.hitTest(x, y);
        this.hover = hit && hit.type !== "scrub" ? hit : null;
        canvas.style.cursor = !hit ? "default"
          : hit.type === "scrub" ? "text"
          : hit.mode === "move" ? "grab" : "ew-resize";
        this.draw();
      });

      const release = event => {
        if (!this.drag) return;
        const wasEdit = !["scrub", "pan"].includes(this.drag.type);
        this.drag = null;
        if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
        canvas.style.cursor = "default";
        if (wasEdit) this.onChange("cues");
        this.draw();
      };
      canvas.addEventListener("pointerup", release);
      canvas.addEventListener("pointercancel", release);
      canvas.addEventListener("lostpointercapture", release);
      canvas.addEventListener("auxclick", event => { if (event.button === 1) event.preventDefault(); });

      canvas.addEventListener("dblclick", event => {
        const { x, y } = this.localPoint(event);
        const hit = this.hitTest(x, y);
        if (hit && hit.type === "word") this.onSeek(hit.words[hit.wordIndex].start);
        else if (hit && hit.type === "phrase") this.onSeek(hit.cue.start);
      });

      canvas.addEventListener("wheel", event => {
        event.preventDefault();
        const { x } = this.localPoint(event);
        if (event.ctrlKey || event.metaKey) {
          this.zoomAt(event.deltaY > 0 ? 1.18 : 0.85, x);
        } else {
          const delta = (event.deltaX || event.deltaY) / 400;
          this.follow = false;
          this.setView(this.viewStart + delta * this.viewSpan, this.viewSpan);
        }
      }, { passive: false });

      window.addEventListener("resize", () => this.resize());
    }

    localPoint(event) {
      const rect = this.canvas.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    updateDrag(x, event) {
      const drag = this.drag;
      if (drag.type === "pan") {
        this.setView(drag.originStart - (x - drag.originX) / Math.max(1, this.width) * this.viewSpan, this.viewSpan);
        return;
      }
      drag.noSnap = event.altKey;
      const pointerTime = this.xToTime(x);
      const delta = pointerTime - drag.startTime;

      if (drag.type === "scrub") {
        this.onSeek(clamp(pointerTime, 0, this.duration()));
        return;
      }

      if (drag.type === "phrase") {
        const cue = drag.cue;
        if (drag.mode === "move") {
          let start = this.applySnap(drag.originStart + delta, cue.id);
          start = Math.max(0, start);
          const shift = start - drag.originStart;
          cue.start = start;
          cue.end = drag.originEnd + shift;
          cue.words = drag.originWords.map(word => ({
            text: word.text, start: word.start + shift, end: word.end + shift
          }));
          if (drag.ripple) {
            for (const item of drag.rippleCues) {
              item.cue.start = item.start + shift;
              item.cue.end = item.end + shift;
              item.cue.words = item.words.map(word => ({
                text: word.text, start: word.start + shift, end: word.end + shift
              }));
            }
          }
        } else if (drag.mode === "start") {
          const start = clamp(this.applySnap(drag.originStart + delta, cue.id), 0, cue.end - MIN_CUE);
          const factor = (drag.originEnd - start) / Math.max(0.01, drag.originEnd - drag.originStart);
          cue.start = start;
          cue.words = drag.originWords.map(word => ({
            text: word.text,
            start: drag.originEnd - (drag.originEnd - word.start) * factor,
            end: drag.originEnd - (drag.originEnd - word.end) * factor
          }));
        } else {
          const end = Math.max(cue.start + MIN_CUE, this.applySnap(drag.originEnd + delta, cue.id));
          const factor = (end - drag.originStart) / Math.max(0.01, drag.originEnd - drag.originStart);
          cue.end = end;
          cue.words = drag.originWords.map(word => ({
            text: word.text,
            start: drag.originStart + (word.start - drag.originStart) * factor,
            end: drag.originStart + (word.end - drag.originStart) * factor
          }));
        }
        this.draw();
        this.onChange("live");
        return;
      }

      // word drag
      const cue = drag.cue;
      const words = cue.words;
      const index = drag.wordIndex;
      const word = words[index];
      const previous = words[index - 1];
      const next = words[index + 1];

      if (drag.mode === "move") {
        let start = this.applySnap(drag.originStart + delta, null);
        const span = drag.originEnd - drag.originStart;
        const lowerBound = previous ? previous.start + MIN_WORD : 0;
        const upperBound = next ? next.end - span - MIN_WORD : Number.MAX_SAFE_INTEGER;
        start = clamp(start, lowerBound, Math.max(lowerBound, upperBound));
        word.start = start;
        word.end = start + span;
        if (previous && previous.end > word.start) previous.end = word.start;
        if (next && next.start < word.end) next.start = word.end;
      } else if (drag.mode === "start") {
        const lowerBound = previous ? previous.start + MIN_WORD : 0;
        word.start = clamp(this.applySnap(drag.originStart + delta, null), lowerBound, word.end - MIN_WORD);
        if (previous) previous.end = Math.max(previous.start + MIN_WORD, word.start);
      } else {
        const upperBound = next ? next.end - MIN_WORD : Number.MAX_SAFE_INTEGER;
        word.end = clamp(this.applySnap(drag.originEnd + delta, null), word.start + MIN_WORD, upperBound);
        if (next) next.start = Math.max(word.end, next.start);
      }

      if (drag.ripple) {
        // Shift every later word by the same amount, keeping their spacing.
        const shift = word.start - drag.originStart;
        for (let i = index + 1; i < words.length; i += 1) {
          words[i].start = drag.words[i].start + shift;
          words[i].end = drag.words[i].end + shift;
        }
      }

      cue.start = Math.min(cue.start, words[0].start);
      cue.end = Math.max(cue.end, words[words.length - 1].end);
      this.draw();
      this.onChange("live");
    }

    /* ---------------------------- rendering ------------------------- */

    resize() {
      const rect = this.host.getBoundingClientRect();
      this.dpr = IS_DESKTOP_HOST ? 1 : Math.min(1.5, window.devicePixelRatio || 1);
      this.width = Math.max(200, Math.floor(rect.width));
      this.height = this.laneTops.bottom + 4;
      this.canvas.width = Math.floor(this.width * this.dpr);
      this.canvas.height = Math.floor(this.height * this.dpr);
      this.canvas.style.width = `${this.width}px`;
      this.canvas.style.height = `${this.height}px`;
      this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
      this.waveCache.key = "";
      this.draw();
      this.onView(this.viewStart, this.viewSpan);
    }

    refreshTheme() {
      this.theme = readTheme(document.documentElement);
      this.waveCache.key = "";
      this.draw();
    }

    tick() {
      const time = this.getTime();
      if (this.follow && !this.drag) {
        const x = this.timeToX(time);
        if (x > this.width * 0.78 || x < this.width * 0.06) {
          this.viewStart = clamp(time - this.viewSpan * 0.35, -0.4, Math.max(0, this.duration()));
          this.onView(this.viewStart, this.viewSpan);
        }
      }
      this.draw(time);
    }

    draw(time) {
      const ctx = this.ctx;
      const state = this.getState();
      const viewKey = `${this.width}:${state.duration}:${this.viewStart}:${this.viewSpan}:${this.follow}`;
      if (viewKey !== this._viewKey) {
        this._viewKey = viewKey;
        this.onView(this.viewStart, this.viewSpan);
      }
      const theme = this.theme;
      const tops = this.laneTops;
      const playhead = time === undefined ? this.getTime() : time;
      this._lastPaintTime = playhead;

      ctx.clearRect(0, 0, this.width, this.height);

      this.drawRuler(ctx, theme, tops, state);
      this.drawWave(ctx, theme, tops, state);
      this.drawPhrases(ctx, theme, tops, state, playhead);
      this.drawWords(ctx, theme, tops, state, playhead);
      if (state.exportRange) {
        const left=this.timeToX(state.exportRange.in-(state.exportOffset||0)),right=this.timeToX(state.exportRange.out-(state.exportOffset||0));
        ctx.fillStyle="#9883ff22";ctx.fillRect(left,0,right-left,this.height);
        ctx.strokeStyle="#b5a6ff";ctx.lineWidth=2;
        for (const [x,label] of [[left,"IN"],[right,"OUT"]]) {
          ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,this.height);ctx.stroke();
          ctx.fillStyle="#b5a6ff";ctx.fillText(label,x+4,12);
        }
      }
      this.drawPlayhead(ctx, theme, tops, playhead);
    }

    drawRuler(ctx, theme, tops, state) {
      ctx.fillStyle = theme.panel2;
      ctx.fillRect(0, 0, this.width, LANES.ruler);
      ctx.strokeStyle = theme.borderSoft;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, LANES.ruler - .5);
      ctx.lineTo(this.width, LANES.ruler - .5);
      ctx.stroke();

      const stepChoices = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1800, 3600];
      const target = this.viewSpan / (this.width / 90);
      const step = stepChoices.find(value => value >= target) || 3600;
      const first = Math.ceil(this.viewStart / step) * step;

      ctx.font = `10px ${theme.font}`;
      ctx.textBaseline = "middle";
      ctx.fillStyle = theme.muted2;
      for (let value = first; value < this.viewStart + this.viewSpan; value += step) {
        const x = this.timeToX(value);
        ctx.fillRect(Math.round(x) + .5, LANES.ruler - 6, 1, 6);
        ctx.fillText(formatTick(value), Math.round(x) + 4, LANES.ruler / 2 - 1);
      }
    }

    drawWave(ctx, theme, tops, state) {
      const top = tops.wave;
      const height = LANES.wave;
      ctx.fillStyle = theme.panel;
      ctx.fillRect(0, top, this.width, height);

      const analysis = state.analysis;
      const middle = top + height / 2;

      if (analysis && analysis.peaks && analysis.peaks.length) {
        const rate = analysis.peaksPerSecond || 60;
        const peaks = analysis.peaks;
        ctx.fillStyle = theme.borderSoft;
        ctx.beginPath();
        for (let x = 0; x < this.width; x += 1) {
          const t0 = this.xToTime(x);
          const t1 = this.xToTime(x + 1);
          const i0 = Math.max(0, Math.floor(t0 * rate));
          const i1 = Math.min(peaks.length - 1, Math.ceil(t1 * rate));
          if (i1 < 0 || i0 >= peaks.length) continue;
          let peak = 0;
          for (let i = i0; i <= i1; i += 1) if (peaks[i] > peak) peak = peaks[i];
          const amplitude = (peak / 255) * (height / 2 - 3);
          ctx.rect(x, middle - amplitude, 1, amplitude * 2 || 1);
        }
        ctx.fill();

        if (state.snapBeats && analysis.bpm > 0) {
          const period = 60 / analysis.bpm;
          const first = Math.ceil((this.viewStart - analysis.beatOffset) / period);
          const last = Math.floor((this.viewStart + this.viewSpan - analysis.beatOffset) / period);
          for (let i = first; i <= last; i += 1) {
            const value = analysis.beatOffset + i * period;
            const x = Math.round(this.timeToX(value)) + .5;
            const downbeat = ((i % 4) + 4) % 4 === 0;
            ctx.strokeStyle = downbeat ? `${theme.accent2}88` : `${theme.muted2}44`;
            ctx.lineWidth = downbeat ? 1.4 : 1;
            ctx.beginPath();
            ctx.moveTo(x, top);
            ctx.lineTo(x, top + height);
            ctx.stroke();
          }
        }

        if (state.snapOnsets !== false && this.viewSpan < 45) {
          ctx.strokeStyle = `${theme.success}9a`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          for (const value of analysis.onsets || []) {
            if (value < this.viewStart || value > this.viewStart + this.viewSpan) continue;
            const x = Math.round(this.timeToX(value)) + .5;
            ctx.moveTo(x, top + height - 9);
            ctx.lineTo(x, top + height - 1);
          }
          ctx.stroke();
        }
      } else {
        ctx.fillStyle = theme.muted2;
        ctx.font = `11px ${theme.font}`;
        ctx.textBaseline = "middle";
        ctx.fillText(
          state.audioLoaded ? "Analyze the audio to display its waveform" : "Load a song to use the timeline",
          12, middle
        );
      }
    }

    drawPhrases(ctx, theme, tops, state, playhead) {
      const top = tops.phrase;
      ctx.fillStyle = theme.panel;
      ctx.fillRect(0, top, this.width, LANES.phrase);

      ctx.font = `600 11px ${theme.font}`;
      ctx.textBaseline = "middle";

      state.cues.forEach((cue, index) => {
        const x1 = this.timeToX(cue.start);
        const x2 = this.timeToX(cue.end);
        if (x2 < -20 || x1 > this.width + 20) return;
        const width = Math.max(2, x2 - x1);
        const selected = cue.id === state.selectedCueId;
        const live = playhead >= cue.start && playhead < cue.end;

        ctx.fillStyle = selected ? `${theme.accent}3a` : live ? `${theme.accent2}2e` : theme.panel3;
        this.roundRect(ctx, x1, top + 3, width, LANES.phrase - 6, 5);
        ctx.fill();
        ctx.strokeStyle = selected ? theme.accent : live ? theme.accent2 : theme.border;
        ctx.lineWidth = selected ? 1.6 : 1;
        ctx.stroke();

        if (width > 34) {
          ctx.save();
          ctx.beginPath();
          ctx.rect(x1 + 6, top, width - 12, LANES.phrase);
          ctx.clip();
          ctx.fillStyle = selected || live ? theme.text : theme.muted;
          const label = `${String(index + 1).padStart(2, "0")} ${cue.text.replace(/\n/g, " ")}`;
          ctx.fillText(label, x1 + 7, top + LANES.phrase / 2);
          ctx.restore();
        }
      });
    }

    drawWords(ctx, theme, tops, state, playhead) {
      const top = tops.word;
      ctx.fillStyle = theme.panel;
      ctx.fillRect(0, top, this.width, LANES.word);

      const cue = state.cues.find(item => item.id === state.selectedCueId);
      if (!cue) {
        ctx.fillStyle = theme.muted2;
        ctx.font = `11px ${theme.font}`;
        ctx.textBaseline = "middle";
        ctx.fillText("Select a phrase to edit individual words", 12, top + LANES.word / 2);
        return;
      }

      const words = this.wordsOf(cue);
      const derived = !(Array.isArray(cue.words) && cue.words.length === words.length);
      ctx.font = `600 11px ${theme.font}`;
      ctx.textBaseline = "middle";

      for (const word of words) {
        const x1 = this.timeToX(word.start);
        const x2 = this.timeToX(word.end);
        if (x2 < -20 || x1 > this.width + 20) continue;
        const width = Math.max(3, x2 - x1);
        const live = playhead >= word.start && playhead < word.end;

        ctx.fillStyle = live ? `${theme.accent}55` : derived ? `${theme.warning}1e` : `${theme.accent2}26`;
        this.roundRect(ctx, x1, top + 4, width, LANES.word - 9, 4);
        ctx.fill();
        ctx.strokeStyle = live ? theme.accent : derived ? `${theme.warning}88` : theme.border;
        ctx.lineWidth = live ? 1.6 : 1;
        ctx.stroke();

        if (width > 18) {
          ctx.save();
          ctx.beginPath();
          ctx.rect(x1 + 3, top, width - 5, LANES.word);
          ctx.clip();
          ctx.fillStyle = live ? theme.text : theme.muted;
          ctx.fillText(word.text, x1 + 4, top + LANES.word / 2);
          ctx.restore();
        }
      }
    }

    drawPlayhead(ctx, theme, tops, playhead) {
      const x = Math.round(this.timeToX(playhead)) + .5;
      if (x < -2 || x > this.width + 2) return;
      ctx.strokeStyle = theme.danger;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, tops.bottom);
      ctx.stroke();
      ctx.fillStyle = theme.danger;
      ctx.beginPath();
      ctx.moveTo(x - 4, 0);
      ctx.lineTo(x + 4, 0);
      ctx.lineTo(x, 6);
      ctx.closePath();
      ctx.fill();
    }

    roundRect(ctx, x, y, width, height, radius) {
      const r = Math.min(radius, width / 2, height / 2);
      ctx.beginPath();
      ctx.moveTo(x + r, y);
      ctx.arcTo(x + width, y, x + width, y + height, r);
      ctx.arcTo(x + width, y + height, x, y + height, r);
      ctx.arcTo(x, y + height, x, y, r);
      ctx.arcTo(x, y, x + width, y, r);
      ctx.closePath();
    }
  }

  window.VFTimeline = { create: options => new Timeline(options), LANES };
})();
