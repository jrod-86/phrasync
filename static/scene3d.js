/*
 * KaraokeSesh 3D scene — an endless themed corridor rendered with a hand-rolled
 * perspective projection on a 2D canvas.
 *
 * There is no mesh pipeline here on purpose: props are declarative primitive
 * lists projected and depth-sorted. Placement is driven by a seeded PRNG keyed
 * on the slot index, which makes the preview world endless and deterministic.
 */
(() => {
  "use strict";

  const SLOT = 7.0;        // world units between prop slots
  const NEAR = 0.9;        // nothing closer than this is drawn
  const FAR = 132.0;       // fog swallows everything past this
  const FOCAL = 1.05;      // lens: screen units per world unit at z = 1

  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const mix = (a, b, t) => a + (b - a) * t;

  /** mulberry32 — small, fast, and trivially portable to Python. */
  function rng(seed) {
    let a = (seed >>> 0) + 0x6d2b79f5;
    return () => {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /**
   * Deterministic 1D value noise: `count` seeded control points, linearly
   * interpolated. Cheap, and it ports to Python with identical output.
   */
  function ridgeProfile(seed, count) {
    const random = rng(seed);
    return Array.from({ length: count }, () => random());
  }

  function sampleProfile(profile, u) {
    const n = profile.length;
    const x = ((u % 1) + 1) % 1 * n;
    const i = Math.floor(x);
    const f = x - i;
    const a = profile[i % n];
    const b = profile[(i + 1) % n];
    return a + (b - a) * (f * f * (3 - 2 * f));
  }

  /* ------------------------------------------------------------------ *
   * Prop kits
   *
   * Local space: origin at the base centre, +y up, roughly 1 unit = 1 world
   * unit. Colour slots resolve against the theme palette at draw time:
   *   0 silhouette   1 structure   2 accent   3 glow   4 paper/light
   * ------------------------------------------------------------------ */

  const KITS = {
    japan: {
      sky: ["#120a1e", "#3a1140", "#7d1f4d"],
      ground: "#0a0611",
      palette: ["#0d0714", "#2a1030", "#ff3d6e", "#ffb84d", "#ffe9c9"],
      skyline: { kind: "peaks", layers: 3, amp: 0.20, colors: ["#2b0f33", "#1d0a26", "#12061a"] },
      celestial: { kind: "moon", x: 0.74, y: 0.30, r: 0.085, color: "#ffe6b8", halo: "#ff9ad1" },
      props: [
        { name: "torii", w: 4.4, h: 5.4, parts: [
          ["rect", -1.8, 0, 0.44, 4.6, 2],
          ["rect", 1.36, 0, 0.44, 4.6, 2],
          ["rect", -2.4, 4.6, 4.8, 0.42, 2],
          ["rect", -2.15, 4.15, 4.3, 0.26, 2],
          ["rect", -0.18, 3.6, 0.36, 0.9, 2],
          ["rect", -2.7, 5.02, 5.4, 0.2, 3]
        ]},
        { name: "lantern", w: 1.1, h: 3.4, parts: [
          ["rect", -0.06, 0, 0.12, 2.1, 1],
          ["ellipse", 0, 2.62, 0.44, 0.56, 4],
          ["rect", -0.34, 2.18, 0.68, 0.12, 2],
          ["rect", -0.34, 2.98, 0.68, 0.12, 2],
          ["glow", 0, 2.62, 1.15, 3]
        ]},
        { name: "banner", w: 1.2, h: 4.6, parts: [
          ["rect", -0.05, 0, 0.1, 4.4, 1],
          ["rect", 0.05, 1.5, 0.62, 2.6, 2],
          ["rect", 0.16, 1.9, 0.4, 0.34, 4],
          ["rect", 0.16, 2.5, 0.4, 0.34, 4],
          ["rect", 0.16, 3.1, 0.4, 0.34, 4]
        ]},
        { name: "pagoda", w: 3.6, h: 6.2, parts: [
          ["rect", -0.9, 0, 1.8, 5.0, 1],
          ["tri", -1.9, 2.0, 1.9, 2.0, 0, 2.9, 2],
          ["tri", -1.6, 3.4, 1.6, 3.4, 0, 4.2, 2],
          ["tri", -1.2, 4.7, 1.2, 4.7, 0, 5.4, 2],
          ["rect", -0.1, 5.4, 0.2, 0.8, 3]
        ]},
        { name: "blossom", w: 3.0, h: 4.4, parts: [
          ["rect", -0.11, 0, 0.22, 2.4, 0],
          ["ellipse", -0.7, 3.0, 0.95, 0.7, 2],
          ["ellipse", 0.6, 3.35, 0.8, 0.62, 2],
          ["ellipse", 0.05, 2.6, 0.75, 0.55, 2]
        ]}
      ]
    },

    italy: {
      sky: ["#0f1224", "#3d2440", "#c56a3e"],
      ground: "#0b0a12",
      palette: ["#0c0a12", "#3a2c38", "#ffb765", "#ff7d4d", "#ffeacb"],
      skyline: { kind: "hills", layers: 3, amp: 0.13, colors: ["#4a2f3c", "#33212c", "#1e141c"] },
      celestial: { kind: "sun", x: 0.28, y: 0.36, r: 0.10, color: "#ffd9a0", halo: "#ff8c4d" },
      props: [
        { name: "arcade", w: 4.6, h: 5.6, parts: [
          ["rect", -2.1, 0, 0.7, 4.4, 1],
          ["rect", 1.4, 0, 0.7, 4.4, 1],
          ["rect", -2.4, 4.4, 4.8, 0.55, 1],
          ["tri", -1.4, 4.4, 1.4, 4.4, 0, 5.5, 1],
          ["rect", -2.5, 4.95, 5.0, 0.18, 2]
        ]},
        { name: "cypress", w: 1.6, h: 6.4, parts: [
          ["rect", -0.12, 0, 0.24, 0.8, 0],
          ["tri", -0.62, 0.6, 0.62, 0.6, 0, 6.3, 0]
        ]},
        { name: "lamp", w: 1.0, h: 4.2, parts: [
          ["rect", -0.09, 0, 0.18, 3.5, 1],
          ["ellipse", 0, 3.78, 0.32, 0.42, 4],
          ["tri", -0.34, 3.95, 0.34, 3.95, 0, 4.3, 1],
          ["glow", 0, 3.78, 1.05, 3]
        ]},
        { name: "roofline", w: 5.2, h: 3.6, parts: [
          ["rect", -2.4, 0, 4.8, 2.5, 1],
          ["tri", -2.7, 2.5, 2.7, 2.5, 0, 3.5, 2],
          ["rect", -1.6, 0.9, 0.5, 0.8, 4],
          ["rect", -0.25, 0.9, 0.5, 0.8, 4],
          ["rect", 1.1, 0.9, 0.5, 0.8, 4]
        ]},
        { name: "urn", w: 1.4, h: 2.0, parts: [
          ["rect", -0.5, 0, 1.0, 0.3, 1],
          ["ellipse", 0, 1.0, 0.5, 0.75, 1],
          ["rect", -0.34, 1.6, 0.68, 0.2, 2]
        ]}
      ]
    },

    china: {
      sky: ["#12061a", "#4a0f2c", "#b8213c"],
      ground: "#0a0510",
      palette: ["#0b0512", "#31112a", "#ff2d4f", "#ffcf4d", "#fff0d4"],
      skyline: { kind: "peaks", layers: 3, amp: 0.24, colors: ["#3a0f27", "#28091c", "#170512" ] },
      celestial: { kind: "moon", x: 0.22, y: 0.26, r: 0.10, color: "#ffd9d0", halo: "#ff2d4f" },
      props: [
        { name: "moongate", w: 5.0, h: 5.4, parts: [
          ["ring", 0, 2.6, 2.3, 0.42, 1],
          ["rect", -2.6, 0, 0.5, 2.6, 1],
          ["rect", 2.1, 0, 0.5, 2.6, 1],
          ["ring", 0, 2.6, 1.9, 0.12, 2]
        ]},
        { name: "lanternRow", w: 2.6, h: 3.8, parts: [
          ["rect", -1.3, 3.5, 2.6, 0.14, 1],
          ["ellipse", -0.85, 2.9, 0.42, 0.5, 2],
          ["ellipse", 0, 2.7, 0.46, 0.55, 2],
          ["ellipse", 0.85, 2.9, 0.42, 0.5, 2],
          ["glow", 0, 2.8, 1.5, 3]
        ]},
        { name: "pagodaTall", w: 4.2, h: 7.4, parts: [
          ["rect", -1.0, 0, 2.0, 6.2, 1],
          ["tri", -2.2, 1.8, 2.2, 1.8, 0, 2.7, 2],
          ["tri", -1.9, 3.3, 1.9, 3.3, 0, 4.1, 2],
          ["tri", -1.6, 4.8, 1.6, 4.8, 0, 5.5, 2],
          ["tri", -1.2, 6.0, 1.2, 6.0, 0, 6.7, 2],
          ["rect", -0.09, 6.7, 0.18, 0.7, 3]
        ]},
        { name: "dragonBanner", w: 1.3, h: 5.0, parts: [
          ["rect", -0.06, 0, 0.12, 4.8, 1],
          ["rect", 0.06, 1.2, 0.7, 3.2, 2],
          ["ellipse", 0.41, 2.2, 0.2, 0.2, 4],
          ["ellipse", 0.41, 3.1, 0.2, 0.2, 4]
        ]}
      ]
    },

    usa: {
      sky: ["#060a18", "#132a4a", "#2f6f8f"],
      ground: "#070910",
      palette: ["#07080f", "#22303f", "#4de2ff", "#ff4d8d", "#e8fbff"],
      skyline: { kind: "city", layers: 2, amp: 0.17, colors: ["#16283a", "#0d1826"] },
      celestial: { kind: "moon", x: 0.78, y: 0.24, r: 0.062, color: "#dff6ff", halo: "#4de2ff" },
      props: [
        { name: "billboard", w: 5.0, h: 6.0, parts: [
          ["rect", -0.2, 0, 0.4, 3.2, 1],
          ["rect", -2.3, 3.0, 4.6, 2.7, 1],
          ["rect", -2.1, 3.2, 4.2, 2.3, 2],
          ["rect", -1.6, 3.7, 3.2, 0.4, 4],
          ["rect", -1.6, 4.5, 2.2, 0.4, 4],
          ["glow", 0, 4.3, 2.6, 3]
        ]},
        { name: "pole", w: 2.6, h: 6.6, parts: [
          ["rect", -0.12, 0, 0.24, 6.4, 0],
          ["rect", -1.2, 5.4, 2.4, 0.16, 0],
          ["rect", -0.95, 4.7, 1.9, 0.14, 0]
        ]},
        { name: "dinerSign", w: 2.2, h: 4.8, parts: [
          ["rect", -0.1, 0, 0.2, 2.6, 1],
          ["ellipse", 0, 3.5, 0.95, 1.1, 2],
          ["ellipse", 0, 3.5, 0.62, 0.75, 1],
          ["tri", -0.5, 2.4, 0.5, 2.4, 0, 1.9, 3],
          ["glow", 0, 3.5, 2.0, 3]
        ]},
        { name: "hydrant", w: 1.0, h: 1.5, parts: [
          ["rect", -0.28, 0, 0.56, 1.0, 3],
          ["ellipse", 0, 1.15, 0.3, 0.28, 3],
          ["rect", -0.45, 0.55, 0.9, 0.14, 1]
        ]}
      ]
    }
  };

  const KIT_ORDER = ["japan", "italy", "china", "usa"];

  /** Directions borrow game-camera language: how the world flows past. */
  const DIRECTIONS = {
    forward: { label: "Forward", rise: 0, sway: 0, roll: 0 },
    ascend: { label: "Ascend", rise: 0.34, sway: 0, roll: 0 },
    dive: { label: "Dive", rise: -0.32, sway: 0, roll: 0 },
    drift: { label: "Drift", rise: 0.05, sway: 1.5, roll: 0.02 },
    bank: { label: "Bank", rise: 0.02, sway: 2.4, roll: 0.075 }
  };

  /* ------------------------------------------------------------------ *
   * Scene sampling
   * ------------------------------------------------------------------ */

  /**
   * Everything visible at time t, already depth sorted far-to-near.
   * Pure data: the browser and the exporter both consume this identically.
   */
  function sample(options) {
    const {
      t, kit = "japan", direction = "forward", seed = 1337,
      speed = 7.0, pulse = 0, density = 1
    } = options;
    const theme = KITS[kit] || KITS.japan;
    const dir = DIRECTIONS[direction] || DIRECTIONS.forward;

    const travel = t * speed;
    const camY = 1.75 + dir.rise * travel * 0.08 + Math.sin(t * 0.31) * 0.12;
    const camX = dir.sway ? Math.sin(t * 0.24) * dir.sway : 0;
    const roll = dir.roll ? Math.sin(t * 0.19) * dir.roll : 0;

    const firstSlot = Math.floor((travel + NEAR) / SLOT);
    const lastSlot = Math.ceil((travel + FAR) / SLOT);
    const items = [];

    for (let slot = firstSlot; slot <= lastSlot; slot += 1) {
      const random = rng(slot * 2654435761 + seed);
      // Near slots get more traffic so the foreground never reads empty.
      const nearBias = clamp(1.35 - (slot * SLOT - travel) / 46, 0.55, 1.35);
      if (random() > (0.34 + 0.46 * density) * nearBias) continue;

      const prop = theme.props[Math.floor(random() * theme.props.length)];
      const side = random() < 0.5 ? -1 : 1;
      const lateral = side * (3.1 + random() * 5.4);
      const scale = 0.6 + Math.pow(random(), 1.7) * 1.7;
      const z = slot * SLOT + (random() - 0.5) * 2.2 - travel;
      if (z < NEAR || z > FAR) continue;

      items.push({
        prop, scale, roll,
        x: lateral - camX,
        y: -camY,
        z,
        // A slow per-prop bob keeps a static kit from reading as a repeated tile.
        bob: Math.sin(t * 0.7 + slot) * 0.08,
        lit: random() < 0.55
      });
    }

    items.sort((a, b) => b.z - a.z);
    return { theme, items, camY, camX, roll, travel, pulse: clamp(pulse) };
  }

  function project(x, y, z, width, height, roll) {
    const f = (FOCAL * height) / z;
    let sx = x * f;
    let sy = -y * f;
    if (roll) {
      const c = Math.cos(roll), s = Math.sin(roll);
      const rx = sx * c - sy * s;
      sy = sx * s + sy * c;
      sx = rx;
    }
    return { x: width / 2 + sx, y: height / 2 + sy, f };
  }

  /** 0 = fully fogged out, 1 = fully present. */
  function depthAlpha(z) {
    return clamp(1 - Math.pow(clamp((z - 10) / (FAR - 10)), 0.85));
  }

  /** Fixed world Z and camera distance for a lyric board due near cue.end. */
  function lyricBoardZ(cueEnd, speed, near = 8) {
    return -cueEnd * speed - near;
  }

  function lyricBoardDistance(cueEnd, t, speed, near = 8) {
    return -t * speed - lyricBoardZ(cueEnd, speed, near);
  }

  window.VFScene = {
    SLOT, NEAR, FAR, FOCAL, KITS, KIT_ORDER, DIRECTIONS,
    rng, sample, project, depthAlpha, clamp, mix, ridgeProfile, sampleProfile,
    lyricBoardZ, lyricBoardDistance
  };
})();
