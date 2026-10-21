"use strict";

// Timeline effects (CapCut-style): clips on the Effects track switch an effect
// on for part of the song. Each effect is drawn from the clip's time alone, so
// the preview and the exported video match frame for frame. Overlay effects
// paint over the background; camera effects move the background itself. Both
// sit under the lyrics, which always stay readable.
window.VFEffects = (() => {
  const CATALOG = [
    { id: "colourful", name: "Colourful", icon: "◐", params: [["speed", "Speed", 40], ["intensity", "Intensity", 35], ["spread", "Colour spread", 60]] },
    { id: "gold-sparkles", name: "Gold Sparkles", icon: "✦", params: [["speed", "Speed", 34], ["amount", "Amount", 50], ["glow", "Glow", 100]] },
    { id: "snow-storm", name: "Snow Storm", icon: "❄", params: [["speed", "Speed", 50], ["amount", "Amount", 60], ["wind", "Wind", 50]] },
    { id: "gold-sequins", name: "Gold Sequins", icon: "⬤", params: [["speed", "Speed", 40], ["amount", "Amount", 50], ["size", "Size", 50]] },
    { id: "pendulum", name: "Pendulum Play", icon: "◠", params: [["speed", "Speed", 40], ["swing", "Swing", 50], ["zoom", "Zoom", 30]] },
    { id: "tremor-strobe", name: "Tremor Strobe", icon: "≋", params: [["speed", "Speed", 50], ["shake", "Shake", 50], ["strobe", "Strobe", 50]] },
    { id: "disco-bounce", name: "Disco Bounce", icon: "✺", params: [["speed", "Speed", 50], ["bounce", "Bounce", 50], ["lights", "Lights", 60]] }
  ];
  const BY_ID = Object.fromEntries(CATALOG.map(item => [item.id, item]));
  const CAMERA = new Set(["pendulum", "tremor-strobe", "disco-bounce"]);
  const RAMP = 0.15;
  const hash = n => ((Math.sin(n * 127.1 + 311.7) * 43758.5453) % 1 + 1) % 1;
  const fract = v => ((v % 1) + 1) % 1;
  const value = (clip, key) => {
    const raw = Number(clip.params?.[key]);
    const fallback = BY_ID[clip.type]?.params.find(param => param[0] === key)?.[2] ?? 50;
    return Math.max(0, Math.min(100, Number.isFinite(raw) ? raw : fallback)) / 100;
  };

  function defaults(type) {
    return Object.fromEntries((BY_ID[type]?.params || []).map(([key, , initial]) => [key, initial]));
  }

  function list(p = project) { return Array.isArray(p.effects) ? p.effects : []; }

  function active(t, p = project) {
    return list(p).filter(clip => BY_ID[clip.type] && t >= clip.start && t < clip.end)
      .sort((a, b) => (a.track || 0) - (b.track || 0) || a.start - b.start);
  }

  /** 0→1→0 over a clip, with a short ramp so effects never pop in or out. */
  function strength(clip, t) {
    return Math.max(0, Math.min(1, (t - clip.start) / RAMP, (clip.end - t) / RAMP));
  }

  function beatPulse(t, rate) {
    const bpm = Number(project.timing?.bpm) || 0;
    const phase = bpm > 0 ? fract((t - (Number(project.timing?.beatOffset) || 0)) * bpm / 60) : fract(t * rate);
    return Math.exp(-phase * 7);
  }

  // ---- camera effects: one combined move of the background --------------
  function camera(t, p = project) {
    const move = { angle: 0, dx: 0, dy: 0, zoom: 1 };
    for (const clip of active(t, p)) {
      if (!CAMERA.has(clip.type)) continue;
      const k = strength(clip, t), local = t - clip.start, speed = value(clip, "speed");
      if (clip.type === "pendulum") {
        move.angle += Math.sin(local * Math.PI * 2 * (0.15 + speed * 0.9)) * value(clip, "swing") * 0.21 * k;
        move.zoom *= 1 + value(clip, "zoom") * 0.12 * k;
      } else if (clip.type === "tremor-strobe") {
        const step = Math.floor(local * (8 + speed * 22)), amount = value(clip, "shake") * 0.035 * k;
        move.dx += (hash(step * 1.7 + 1) - 0.5) * 2 * amount;
        move.dy += (hash(step * 2.3 + 7) - 0.5) * 2 * amount;
        move.angle += (hash(step * 3.1 + 3) - 0.5) * amount * 0.6;
      } else if (clip.type === "disco-bounce") {
        const pulse = beatPulse(local, 1 + speed * 2.4);
        move.zoom *= 1 + value(clip, "bounce") * 0.14 * pulse * k;
        move.dy -= value(clip, "bounce") * 0.02 * pulse * k;
      }
    }
    return move;
  }

  /** Redraw what is already on ctx through the camera move (covering the corners). */
  function applyCamera(ctx, t, background = "#080812") {
    const move = camera(t);
    if (!move.angle && !move.dx && !move.dy && move.zoom === 1) return;
    const { width: w, height: h } = ctx.canvas;
    const scratch = applyCamera.scratch ||= document.createElement("canvas");
    if (scratch.width !== w || scratch.height !== h) { scratch.width = w; scratch.height = h; }
    const copy = scratch.getContext("2d");
    copy.clearRect(0, 0, w, h); copy.drawImage(ctx.canvas, 0, 0);
    const cover = Math.abs(Math.cos(move.angle)) + Math.abs(Math.sin(move.angle)) * Math.max(w / h, h / w);
    const scale = move.zoom * cover * (1 + 2 * Math.max(Math.abs(move.dx), Math.abs(move.dy)));
    ctx.save();
    ctx.fillStyle = background; ctx.fillRect(0, 0, w, h);
    ctx.translate(w / 2 + move.dx * w, h / 2 + move.dy * h);
    ctx.rotate(move.angle); ctx.scale(scale, scale);
    ctx.drawImage(scratch, -w / 2, -h / 2);
    ctx.restore();
  }

  // ---- overlay effects ----------------------------------------------------
  function colourful(ctx, clip, t, k) {
    const { width: w, height: h } = ctx.canvas, local = t - clip.start;
    const hue = local * (10 + value(clip, "speed") * 120), spread = 40 + value(clip, "spread") * 200;
    const angle = local * (0.2 + value(clip, "speed") * 0.8);
    const fill = ctx.createLinearGradient(w / 2 - Math.cos(angle) * w, h / 2 - Math.sin(angle) * h, w / 2 + Math.cos(angle) * w, h / 2 + Math.sin(angle) * h);
    for (let i = 0; i <= 4; i++) fill.addColorStop(i / 4, `hsl(${(hue + spread * i / 4) % 360} 95% 55%)`);
    ctx.globalCompositeOperation = "overlay";
    ctx.globalAlpha = value(clip, "intensity") * 0.95 * k;
    ctx.fillStyle = fill; ctx.fillRect(0, 0, w, h);
  }

  function star(ctx, x, y, r) {
    ctx.beginPath();
    for (let i = 0; i < 8; i++) {
      const a = i * Math.PI / 4, len = i % 2 ? r * 0.22 : r;
      ctx.lineTo(x + Math.cos(a) * len, y + Math.sin(a) * len);
    }
    ctx.closePath(); ctx.fill();
  }

  function goldSparkles(ctx, clip, t, k) {
    const { width: w, height: h } = ctx.canvas, unit = Math.min(w, h) / 1080, local = t - clip.start;
    const count = Math.round(20 + value(clip, "amount") * 160), rate = 0.25 + value(clip, "speed") * 1.6;
    ctx.globalCompositeOperation = "lighter";
    ctx.shadowColor = "#ffcc4d"; ctx.shadowBlur = value(clip, "glow") * 22 * unit;
    for (let i = 0; i < count; i++) {
      const life = fract(local * rate * (0.6 + hash(i + 9) * 0.8) + hash(i + 3));
      const cycle = Math.floor(local * rate * (0.6 + hash(i + 9) * 0.8) + hash(i + 3));
      const x = hash(i * 13.7 + cycle * 3.1) * w, y = fract(hash(i * 7.9 + cycle * 5.3) - life * 0.04) * h;
      const twinkle = Math.sin(life * Math.PI) ** 2;
      ctx.globalAlpha = twinkle * k * (0.55 + hash(i + 21) * 0.45);
      ctx.fillStyle = hash(i + 5) > 0.35 ? "#ffd56a" : "#fff3c4";
      star(ctx, x, y, (6 + hash(i + 2) * 16) * unit * (0.6 + twinkle * 0.6));
    }
  }

  function snowStorm(ctx, clip, t, k) {
    const { width: w, height: h } = ctx.canvas, unit = Math.min(w, h) / 1080, local = t - clip.start;
    const count = Math.round(60 + value(clip, "amount") * 440), fall = 0.08 + value(clip, "speed") * 0.5;
    const wind = (value(clip, "wind") - 0.15) * 0.6;
    ctx.globalAlpha = value(clip, "amount") * 0.12 * k;
    ctx.fillStyle = "#e8f1ff"; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#ffffff";
    for (let i = 0; i < count; i++) {
      const depth = 0.35 + hash(i + 17) * 0.65;
      const y = fract(hash(i + 1) + local * fall * depth);
      const x = fract(hash(i + 31) + local * wind * depth + Math.sin(local * 1.3 + i) * 0.012);
      ctx.globalAlpha = (0.35 + depth * 0.6) * k;
      ctx.beginPath(); ctx.arc(x * w, y * h, (1.2 + depth * 4.5) * unit, 0, Math.PI * 2); ctx.fill();
    }
  }

  function goldSequins(ctx, clip, t, k) {
    const { width: w, height: h } = ctx.canvas, unit = Math.min(w, h) / 1080, local = t - clip.start;
    const count = Math.round(25 + value(clip, "amount") * 175), fall = 0.05 + value(clip, "speed") * 0.3;
    const size = (5 + value(clip, "size") * 16) * unit;
    for (let i = 0; i < count; i++) {
      const depth = 0.5 + hash(i + 8) * 0.5;
      const y = fract(hash(i + 4) + local * fall * depth);
      const x = fract(hash(i + 12) + Math.sin(local * 0.9 + i * 2.1) * 0.03);
      const spin = local * (2 + hash(i + 6) * 5) + hash(i) * 6.28;
      const face = Math.cos(spin), shine = Math.max(0, face) ** 6;
      ctx.save();
      ctx.translate(x * w, y * h); ctx.rotate(hash(i + 15) * Math.PI);
      ctx.globalAlpha = k * (0.75 + depth * 0.25);
      ctx.fillStyle = `hsl(${42 + hash(i + 1) * 8} ${80 + shine * 15}% ${32 + Math.abs(face) * 30 + shine * 30}%)`;
      ctx.beginPath(); ctx.ellipse(0, 0, size * depth, Math.max(0.6, size * depth * Math.abs(face)), 0, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    }
  }

  function tremorStrobe(ctx, clip, t, k) {
    const local = t - clip.start, rate = 2 + value(clip, "speed") * 10;
    const flash = fract(local * rate) < 0.22 ? 1 : 0;
    if (!flash) return;
    ctx.globalCompositeOperation = "screen";
    ctx.globalAlpha = value(clip, "strobe") * 0.85 * k;
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
  }

  function discoBounce(ctx, clip, t, k) {
    const { width: w, height: h } = ctx.canvas, local = t - clip.start, speed = value(clip, "speed");
    const lights = value(clip, "lights");
    if (!lights) return;
    const pulse = beatPulse(local, 1 + speed * 2.4);
    ctx.globalCompositeOperation = "screen";
    for (let i = 0; i < 4; i++) {
      const a = local * (0.4 + speed * 1.2) * (i % 2 ? -1 : 1) + i * 1.57;
      const x = w * (0.5 + Math.cos(a) * 0.38), y = h * (0.5 + Math.sin(a * 1.3) * 0.32), r = Math.max(w, h) * 0.32;
      const glow = ctx.createRadialGradient(x, y, 0, x, y, r);
      glow.addColorStop(0, `hsl(${(i * 90 + local * 60) % 360} 100% 60% / 1)`);
      glow.addColorStop(1, `hsl(${(i * 90 + local * 60) % 360} 100% 50% / 0)`);
      ctx.globalAlpha = lights * (0.35 + pulse * 0.45) * k;
      ctx.fillStyle = glow; ctx.fillRect(0, 0, w, h);
    }
  }

  const OVERLAYS = { colourful, "gold-sparkles": goldSparkles, "snow-storm": snowStorm, "gold-sequins": goldSequins,
    "tremor-strobe": tremorStrobe, "disco-bounce": discoBounce };

  function drawOverlay(ctx, t) {
    for (const clip of active(t)) {
      const draw = OVERLAYS[clip.type];
      if (!draw) continue;
      ctx.save(); draw(ctx, clip, t, strength(clip, t)); ctx.restore();
    }
  }

  return { CATALOG, BY_ID, defaults, list, active, camera, applyCamera, drawOverlay };
})();
