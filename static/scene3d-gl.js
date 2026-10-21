/*
 * Odyssey 3D — a real WebGL flythrough for KaraokeSesh.
 *
 * Everything here is a pure function of the playback clock: given the same t the
 * scene composes identically, which is what lets the exporter render frames out
 * of a headless browser and get exactly what the editor showed. Nothing
 * accumulates between frames, so scrubbing the timeline never desynchronises the
 * world.
 */
import * as THREE from "/static/vendor/three.module.min.js";
import { createEnvironment, updateEnvironment } from "/static/scene3d-environment.js";
import { createWorld, updateWorld, sceneryPoint } from "/static/scene3d-world.js";
import { createExpeditions, updateExpeditions } from "/static/scene3d-expeditions.js";
import { createOcean, updateOcean, updateOceanCamera } from "/static/scene3d-ocean.js";

const SLOT = 24;         // reserved landmark plots; context furniture sits between rows
const VISIBLE_SLOTS = 11; // eleven 24-unit plots match the contextual world's 264-unit cycle
const PROTOTYPES_PER_SLOT = 4;

const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const clampAngle = (v, limit) => Math.min(limit, Math.max(-limit, v));

// Reading distance at the phrase end; after that the world carries it through
// the near plane and behind the viewer.
const BOARD_NEAR = 8;

/** mulberry32, matching static/scene3d.js so seeds behave the same everywhere. */
function rng(seed) {
  let a = (seed >>> 0) + 0x6d2b79f5;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ---------------------------------------------------------------- themes -- */

const THEMES = {
  japan: {
    fog: 0x1a0a24, sky: [0x2a0f3a, 0x7d1f4d], ground: 0x120a1a,
    key: 0xff3d6e, warm: 0xffb84d, cool: 0xb06bff, moon: 0xffe6b8,
    ridge: 0x2b0f33, builders: ["torii", "stoneLantern", "pagoda", "cherry"]
  },
  italy: {
    fog: 0x241a20, sky: [0x2b1d33, 0xc56a3e], ground: 0x14100f,
    key: 0xffb765, warm: 0xff7d4d, cool: 0x6f7bb5, moon: 0xffd9a0,
    ridge: 0x4a2f3c, builders: ["arch", "cypress", "lamp", "roofline"]
  },
  china: {
    fog: 0x1c0616, sky: [0x370a24, 0xb8213c], ground: 0x120510,
    key: 0xff2d4f, warm: 0xffcf4d, cool: 0xff7ab0, moon: 0xffd9d0,
    ridge: 0x3a0f27, builders: ["moonGate", "lanternRow", "pagodaTall", "cypress"]
  },
  usa: {
    fog: 0x0a1420, sky: [0x0d1c33, 0x2f6f8f], ground: 0x0a0e14,
    key: 0x4de2ff, warm: 0xff4d8d, cool: 0x6f8dff, moon: 0xdff6ff,
    ridge: 0x16283a, builders: ["billboard", "pole", "dinerSign", "roofline"]
  }
};

const DIRECTIONS = {
  left: { rise: 0, sway: 0, roll: 0, look: 0 },
  right: { rise: 0, sway: 0, roll: 0, look: 0 },
  up: { rise: 0, sway: 0, roll: 0, look: 0 },
  down: { rise: 0, sway: 0, roll: 0, look: 0 },
  forward: { rise: 0, sway: 0, roll: 0, look: 0 },
  ascend: { rise: 0.9, sway: 0, roll: 0, look: 0.10 },
  dive: { rise: -0.8, sway: 0, roll: 0, look: -0.10 },
  drift: { rise: 0.1, sway: 3.0, roll: 0.04, look: 0 },
  bank: { rise: 0.05, sway: 4.4, roll: 0.14, look: 0 }
};

/* ------------------------------------------------------------ materials -- */

function makeMaterials(theme) {
  const solid = colour => new THREE.MeshStandardMaterial({
    color: colour, roughness: 0.85, metalness: 0.05
  });
  const emissive = (colour, strength = 1.6) => new THREE.MeshStandardMaterial({
    color: colour, emissive: colour, emissiveIntensity: strength,
    roughness: 0.4, metalness: 0
  });
  const foliage = solid(0x1d2b22);
  foliage.userData.environmentRole = "foliage";
  return {
    dark: solid(0x14101c),
    stone: solid(theme.kit === 'japan' ? 0xb29d7e : theme.kit === 'china' ? 0xc6bb9d : theme.kit === 'italy' ? 0xc6af8b : 0x68737d),
    roof: solid(theme.kit === 'italy' ? 0xa65a3c : 0x34404a),
    wood: solid(theme.kit === 'china' ? 0x8e382c : 0x5b4334),
    key: solid(['japan','china'].includes(theme.kit) ? 0xa94432 : theme.key),
    warm: emissive(theme.warm, 2.1),
    keyGlow: emissive(theme.key, 1.5),
    paper: emissive(0xfff0d0, 1.2),
    foliage
  };
}

/** Additive sprite standing in for a bloom pass we would otherwise have to vendor. */
function glowSprite(colour, size) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.35, "rgba(255,255,255,.42)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 128, 128);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: new THREE.CanvasTexture(canvas),
    color: colour,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
    transparent: true,
    fog: false
  }));
  sprite.scale.setScalar(size);
  return sprite;
}

/* ------------------------------------------------------------- builders -- */

const BUILDERS = {
  torii(m, theme) {
    const group = new THREE.Group();
    const post = new THREE.CylinderGeometry(0.28, 0.34, 6, 10);
    for (const x of [-2.2, 2.2]) {
      const leg = new THREE.Mesh(post, m.key);
      leg.position.set(x, 3, 0);
      leg.rotation.z = x > 0 ? -0.03 : 0.03;
      group.add(leg);
    }
    const top = new THREE.Mesh(new THREE.BoxGeometry(6.4, 0.42, 0.6), m.key);
    top.position.y = 6.1;
    group.add(top);
    const cap = new THREE.Mesh(new THREE.BoxGeometry(7.2, 0.3, 0.8), m.warm);
    cap.position.y = 6.6;
    group.add(cap);
    const tie = new THREE.Mesh(new THREE.BoxGeometry(5.2, 0.3, 0.45), m.key);
    tie.position.y = 5.3;
    group.add(tie);
    const plaque = new THREE.Mesh(new THREE.BoxGeometry(0.7, 1.0, 0.2), m.warm);
    plaque.position.y = 5.7;
    group.add(plaque);
    return group;
  },

  stoneLantern(m, theme) {
    const group = new THREE.Group();
    const base = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.6, 0.5, 8), m.stone);
    base.position.y = 0.25; group.add(base);
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.26, 2.2, 8), m.stone);
    shaft.position.y = 1.5; group.add(shaft);
    const house = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.9, 1.0), m.paper);
    house.position.y = 3.0; group.add(house);
    const roof = new THREE.Mesh(new THREE.ConeGeometry(1.0, 0.7, 4), m.stone);
    roof.position.y = 3.75; roof.rotation.y = Math.PI / 4; group.add(roof);
    const glow = glowSprite(theme.warm, 4.2);
    glow.position.y = 3.0; group.add(glow);
    return group;
  },

  pagoda(m, theme) {
    const group = new THREE.Group();
    const foot = new THREE.Mesh(new THREE.BoxGeometry(4.4, .35, 4.4), m.stone);
    foot.position.y=.175;group.add(foot);
    for (let i = 0; i < 4; i += 1) {
      const width = 2.8-i*.42, y=.4+i*1.9;
      const body = new THREE.Mesh(new THREE.BoxGeometry(width,1.2,width),m.wood);
      body.position.y=y+.6;group.add(body);
      const panel = new THREE.Mesh(new THREE.BoxGeometry(width*.75,.64,width+.02),m.stone);
      panel.position.y=y+.62;group.add(panel);
      const eave = new THREE.Mesh(new THREE.ConeGeometry(3.5-i*.46,.9,4),m.roof);
      eave.position.y=y+1.45;
      eave.rotation.y = Math.PI / 4;
      group.add(eave);
    }
    const finial = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.12, 1.2, 6), m.warm);
    finial.position.y = 8.3; group.add(finial);
    return group;
  },

  cherry(m, theme) {
    const group = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.3, 3.4, 7), m.dark);
    trunk.position.y = 1.7; group.add(trunk);
    const blossomMaterial = new THREE.MeshStandardMaterial({
      color: theme.key, emissive: theme.key, emissiveIntensity: 0.35, roughness: 1
    });
    const random = rng(77);
    for (let i = 0; i < 7; i += 1) {
      const puff = new THREE.Mesh(new THREE.SphereGeometry(0.9 + random() * 0.7, 7, 6), blossomMaterial);
      puff.position.set((random() - 0.5) * 2.8, 3.4 + random() * 1.8, (random() - 0.5) * 2.2);
      puff.scale.y = 0.75;
      group.add(puff);
    }
    return group;
  },

  arch(m, theme) {
    const group = new THREE.Group();
    for (const x of [-2.4, 2.4]) {
      const column = new THREE.Mesh(new THREE.CylinderGeometry(0.42, 0.5, 5, 12), m.stone);
      column.position.set(x, 2.5, 0); group.add(column);
    }
    const arc = new THREE.Mesh(new THREE.TorusGeometry(2.4, 0.42, 8, 18, Math.PI), m.stone);
    arc.position.y = 5; group.add(arc);
    const lintel = new THREE.Mesh(new THREE.BoxGeometry(6.2, 0.5, 1.2), m.stone);
    lintel.position.y = 7.6; group.add(lintel);
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.24, 8, 8), m.warm);
    lamp.position.y = 5.1; group.add(lamp);
    const archGlow = glowSprite(theme.warm, 3.4);
    archGlow.position.set(0, 5.1, 0);
    group.add(archGlow);
    return group;
  },

  cypress(m) {
    const group = new THREE.Group();
    const trunk = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.2, 1, 6), m.dark);
    trunk.position.y = 0.5; group.add(trunk);
    const body = new THREE.Mesh(new THREE.ConeGeometry(0.9, 7.5, 9), m.foliage);
    body.position.y = 4.4; group.add(body);
    return group;
  },

  lamp(m, theme) {
    const group = new THREE.Group();
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.14, 4.6, 8), m.dark);
    post.position.y = 2.3; group.add(post);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.3, 10, 10), m.warm);
    head.position.y = 4.8; group.add(head);
    const hat = new THREE.Mesh(new THREE.ConeGeometry(0.42, 0.4, 8), m.dark);
    hat.position.y = 5.2; group.add(hat);
    const glow = glowSprite(theme.warm, 4.8);
    glow.position.y = 4.8; group.add(glow);
    return group;
  },

  roofline(m, theme) {
    const group = new THREE.Group();
    const block = new THREE.Mesh(new THREE.BoxGeometry(6, 5.2, 5), m.stone);
    block.position.y = 2.6; group.add(block);
    const roof = new THREE.Mesh(new THREE.ConeGeometry(4.6, 1.8, 4), m.key);
    roof.position.y = 6.1; roof.rotation.y = Math.PI / 4; group.add(roof);
    const random = rng(31);
    for (let i = 0; i < 5; i += 1) {
      const window_ = new THREE.Mesh(new THREE.BoxGeometry(0.6, 0.9, 0.1), m.paper);
      window_.position.set(-2 + i * 1.0, 1.6 + Math.floor(random() * 2) * 1.6, 2.55);
      group.add(window_);
    }
    return group;
  },

  moonGate(m, theme) {
    const group = new THREE.Group();
    const ring = new THREE.Mesh(new THREE.TorusGeometry(3, 0.45, 10, 28), m.stone);
    ring.position.y = 3.4; group.add(ring);
    const inner = new THREE.Mesh(new THREE.TorusGeometry(2.5, 0.1, 8, 28), m.keyGlow);
    inner.position.y = 3.4; group.add(inner);
    for (const x of [-3.1, 3.1]) {
      const pier = new THREE.Mesh(new THREE.BoxGeometry(0.7, 3.6, 0.9), m.stone);
      pier.position.set(x, 1.8, 0); group.add(pier);
    }
    return group;
  },

  lanternRow(m, theme) {
    const group = new THREE.Group();
    const wire = new THREE.Mesh(new THREE.BoxGeometry(6, 0.06, 0.06), m.dark);
    wire.position.y = 5.2; group.add(wire);
    for (let i = -2; i <= 2; i += 1) {
      const lantern = new THREE.Mesh(new THREE.SphereGeometry(0.42, 12, 10), m.keyGlow);
      lantern.scale.y = 1.25;
      lantern.position.set(i * 1.4, 4.5 - Math.abs(i) * 0.12, 0);
      group.add(lantern);
      const glow = glowSprite(theme.key, 3.0);
      glow.position.copy(lantern.position);
      group.add(glow);
    }
    return group;
  },

  pagodaTall(m, theme) {
    const group = BUILDERS.pagoda(m, theme);
    group.scale.set(1.15, 1.5, 1.15);
    return group;
  },

  billboard(m, theme) {
    const group = new THREE.Group();
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.4, 5, 0.4), m.dark);
    leg.position.y = 2.5; group.add(leg);
    const panel = new THREE.Mesh(new THREE.BoxGeometry(6.4, 3.4, 0.25), m.keyGlow);
    panel.position.y = 6.4; group.add(panel);
    const frame = new THREE.Mesh(new THREE.BoxGeometry(6.9, 3.9, 0.15), m.dark);
    frame.position.set(0, 6.4, -0.12); group.add(frame);
    const glow = glowSprite(theme.key, 9);
    glow.position.y = 6.4; group.add(glow);
    return group;
  },

  pole(m) {
    const group = new THREE.Group();
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.18, 9, 7), m.dark);
    post.position.y = 4.5; group.add(post);
    for (const [y, w] of [[7.6, 3.4], [6.6, 2.8]]) {
      const arm = new THREE.Mesh(new THREE.BoxGeometry(w, 0.14, 0.14), m.dark);
      arm.position.y = y; group.add(arm);
    }
    return group;
  },

  dinerSign(m, theme) {
    const group = new THREE.Group();
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 4, 8), m.dark);
    post.position.y = 2; group.add(post);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(1.3, 0.16, 8, 22), m.warm);
    ring.position.y = 5.2; group.add(ring);
    const disc = new THREE.Mesh(new THREE.CircleGeometry(1.15, 22), m.keyGlow);
    disc.position.set(0, 5.2, 0.05); group.add(disc);
    const glow = glowSprite(theme.warm, 7);
    glow.position.y = 5.2; group.add(glow);
    return group;
  }
};

/* ------------------------------------------------------------- backdrop -- */

function makeBackdrop(theme) {
  const canvas = document.createElement("canvas");
  canvas.width = 32; canvas.height = 512;
  const ctx = canvas.getContext("2d");
  const gradient = ctx.createLinearGradient(0, 0, 0, 512);
  gradient.addColorStop(0, "#" + theme.sky[0].toString(16).padStart(6, "0"));
  gradient.addColorStop(0.62, "#" + theme.sky[1].toString(16).padStart(6, "0"));
  gradient.addColorStop(1, "#" + theme.fog.toString(16).padStart(6, "0"));
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 32, 512);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/** Star field and moon live on a dome that rides with the camera. */
function makeSky(theme) {
  const group = new THREE.Group();
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(400, 24, 16),
    new THREE.MeshBasicMaterial({ map: makeBackdrop(theme), side: THREE.BackSide, depthWrite: false, fog: false })
  );
  group.add(dome);

  const random = rng(9001);
  const positions = [];
  for (let i = 0; i < 700; i += 1) {
    const theta = random() * Math.PI * 2;
    const phi = Math.acos(clamp(random() * 0.9 + 0.05, -1, 1));
    const r = 380;
    positions.push(
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.cos(phi) * 0.9,
      r * Math.sin(phi) * Math.sin(theta)
    );
  }
  const stars = new THREE.Points(
    new THREE.BufferGeometry().setAttribute("position", new THREE.Float32BufferAttribute(positions, 3)),
    new THREE.PointsMaterial({ color: 0xffffff, size: 2.2, sizeAttenuation: false, transparent: true, opacity: 0.75, depthWrite: false, fog: false })
  );
  group.add(stars);

  const moon = glowSprite(theme.moon, 120);
  moon.position.set(-160, 120, -350);
  group.add(moon);
  const disc = new THREE.Mesh(
    new THREE.CircleGeometry(26, 32),
    new THREE.MeshBasicMaterial({ color: theme.moon, depthWrite: false, fog: false })
  );
  disc.position.copy(moon.position);
  group.add(disc);

  return group;
}

/** Distant ridge silhouettes, three parallax bands of extruded noise. */
function makeRidges(theme) {
  const group = new THREE.Group();
  for (let layer = 0; layer < 3; layer += 1) {
    const points = [];
    const span = 900;
    const steps = 240;
    const amp = 20 + layer * 19;
    for (let i = 0; i <= steps; i += 1) {
      const x = -span / 2 + (i / steps) * span;
      const h = .52 + .25 * Math.sin(x * .022 + layer * 2)
        + .14 * Math.sin(x * .041 + layer) + .07 * Math.sin(x * .091);
      points.push(new THREE.Vector2(x, h * amp));
    }
    const shape = new THREE.Shape();
    shape.moveTo(points[0].x, -60);
    for (const p of points) shape.lineTo(p.x, p.y);
    shape.lineTo(points[points.length - 1].x, -60);
    shape.closePath();
    const colour = new THREE.Color(theme.ridge).lerp(new THREE.Color(theme.fog), layer * 0.3);
    const mesh = new THREE.Mesh(
      new THREE.ShapeGeometry(shape),
      new THREE.MeshBasicMaterial({ color: colour, depthWrite: false, fog: true })
    );
    mesh.userData.parallax = 0.03 - layer * 0.009;
    mesh.userData.depth = layer * 70;
    group.add(mesh);
  }
  return group;
}


/* ------------------------------------------------------------ lyric text -- */

const ARRIVALS = ["depth", "left", "right", "top", "depth", "spin"];
const textureCache = new Map();

/** Render one word to a canvas and keep it around; words repeat constantly. */
function wordTexture(text, style) {
  const key = `${text}|${style.font}|${style.color}|${style.accent}|${style.stroke}|${style.strokeWidth}`;
  const cached = textureCache.get(key);
  if (cached) return cached;

  const size = 128;
  const probe = document.createElement("canvas").getContext("2d");
  probe.font = `900 ${size}px ${style.font}`;
  const width = Math.ceil(probe.measureText(text).width);
  const pad = Math.ceil(size * 0.34);

  const canvas = document.createElement("canvas");
  canvas.width = Math.max(2, width + pad * 2);
  canvas.height = Math.max(2, Math.ceil(size * 1.5) + pad);
  const ctx = canvas.getContext("2d");
  ctx.font = `900 ${size}px ${style.font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const cx = canvas.width / 2;
  const cy = canvas.height / 2;

  ctx.shadowColor = "rgba(0,0,0,.85)";
  ctx.shadowBlur = size * 0.22;
  ctx.shadowOffsetY = size * 0.05;
  if (style.strokeWidth > 0) {
    ctx.lineWidth = style.strokeWidth * (size / 100);
    ctx.strokeStyle = style.stroke;
    ctx.lineJoin = "round";
    ctx.strokeText(text, cx, cy);
  }
  ctx.shadowBlur = 0;
  ctx.shadowOffsetY = 0;
  ctx.fillStyle = style.color;
  ctx.fillText(text, cx, cy);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const entry = { texture, aspect: canvas.width / canvas.height };
  textureCache.set(key, entry);
  return entry;
}

/** Same word, drawn in the accent colour, for the sung state. */
function accentStyle(style) {
  return { ...style, color: style.accent };
}

function hashKey(value) {
  let h = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}


/**
 * A word with real depth: the glyph texture repeated back along -z, each copy
 * darker than the last. Under perspective and rotation this reads as extruded
 * type, and unlike TextGeometry it works with every font the app can load,
 * including the user's own uploaded TTF.
 */
function buildWordSlab(text, style, unit) {
  const group = new THREE.Group();
  const front = wordTexture(text, style);
  const accent = wordTexture(text, accentStyle(style));
  const layers = 12;
  const step = 0.032;
  const width = front.aspect * 0.68;

  for (let i = layers - 1; i >= 0; i -= 1) {
    const isFace = i === 0;
    const shade = isFace ? 1 : 0.30 - (i / layers) * 0.22;
    const material = new THREE.MeshBasicMaterial({
      map: front.texture,
      color: isFace ? 0xffffff : new THREE.Color(shade * 1.15, shade * 0.55, shade * 0.85),
      transparent: true,
      depthWrite: false,
      depthTest: true,
      fog: true,
      toneMapped: false,
      side: THREE.DoubleSide
    });
    const plane = new THREE.Mesh(new THREE.PlaneGeometry(width, 1), material);
    plane.position.z = -i * step;
    plane.userData = {
      alpha: isFace ? 1 : 0.96,
      face: isFace,
      baseMap: front.texture,
      accentMap: accent.texture
    };
    plane.renderOrder = 10 - i * 0.01;
    group.add(plane);
  }
  return group;
}


/* ------------------------------------------------------------ wave field -- */

const WAVE_COLS = 110;
const WAVE_ROWS = 52;

/**
 * A particle sheet flanking the road whose surface is driven by the live
 * spectrum: low bins sit at the centre lane, highs spread outward. It is
 * rebuilt from t and the spectrum every frame with no history buffer, so
 * scrubbing and the deterministic exporter both stay honest.
 */
function makeWaveField(colour) {
  const count = WAVE_COLS * WAVE_ROWS;
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  const material = new THREE.PointsMaterial({
    size: 0.26,
    sizeAttenuation: true,
    vertexColors: true,
    transparent: true,
    opacity: 0.92,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    fog: true
  });
  const points = new THREE.Points(geometry, material);
  points.frustumCulled = false;
  points.userData.base = new THREE.Color(colour);
  return points;
}

function updateWaveField(points, t, camZ, spectrum, colour, intensity, pulse) {
  const position = points.geometry.attributes.position;
  const colours = points.geometry.attributes.color;
  const base = points.userData.base.set(colour);
  const hot = new THREE.Color(0xffffff);
  const bins = spectrum && spectrum.length ? spectrum.length : 0;

  let index = 0;
  for (let row = 0; row < WAVE_ROWS; row += 1) {
    const depth = row / (WAVE_ROWS - 1);
    const z = camZ - 3 - depth * 96;
    // Distant rows are compressed, which reads as perspective on the fluid.
    const fade = 1 - depth * 0.65;
    for (let col = 0; col < WAVE_COLS; col += 1) {
      const u = col / (WAVE_COLS - 1);
      const x = (u - 0.5) * 54;
      const lane = Math.abs(u - 0.5) * 2;

      // Centre lane follows the bass, the edges follow the highs.
      const bin = bins ? Math.min(bins - 1, Math.floor(lane * bins * 0.85)) : 0;
      const level = bins ? spectrum[bin] : 0.18 + 0.12 * Math.sin(t * 1.7 + lane * 5);

      // Two crossing wave trains at different rates never repeat cleanly, which
      // is what keeps the surface reading as fluid rather than as a grid.
      const travel = t * 2.4;
      const swellA = Math.sin(u * 7.3 + travel * 1.4 + depth * 4.1);
      const swellB = Math.sin(u * 3.1 - travel * 0.9 + depth * 9.4);
      const ripple = swellA * 0.62 + swellB * 0.38;
      const energy = (0.30 + level * 1.9) * (1.4 + intensity * 2.6);
      const y = 0.1 + energy * (0.45 + 0.55 * ripple) * (0.4 + 0.6 * fade);

      position.array[index] = x;
      position.array[index + 1] = y;
      position.array[index + 2] = z;

      const heat = clamp(level * 1.3 + Math.max(0, ripple) * 0.45 + pulse * 0.2);
      const r = base.r + (hot.r - base.r) * heat;
      const g = base.g + (hot.g - base.g) * heat;
      const b = base.b + (hot.b - base.b) * heat;
      const dim = 0.25 + 0.75 * fade;
      colours.array[index] = r * dim;
      colours.array[index + 1] = g * dim;
      colours.array[index + 2] = b * dim;
      index += 3;
    }
  }
  position.needsUpdate = true;
  colours.needsUpdate = true;
}


/* --------------------------------------------------------- 3D personalities -- */

/**
 * How each style preset behaves in the 3D scene.
 *
 * Without this every preset produced the same board with a randomly chosen
 * entry direction, so switching style changed nothing you could see. Each entry
 * drives line breaking, depth staggering, size and the way words arrive.
 */
const PERSONALITY = {
  "spiral": {charsPerLine:1,sizeBoost:2,depthStep:0,arrival:"spiral",overshoot:0,spin:0,farBoost:1},
  "constellation": {charsPerLine:1,sizeBoost:1.7,depthStep:1.5,arrival:"scatter",overshoot:0,spin:0,farBoost:1},
  "kinetic-slam": {
    charsPerLine: 15, sizeBoost: 1.0, depthStep: 0, arrival: "punch",
    overshoot: 0.34, spin: 0.0, farBoost: 1.0
  },
  "neon-flux": {
    charsPerLine: 18, sizeBoost: 0.95, depthStep: 1.1, arrival: "drift",
    overshoot: 0.0, spin: 0.10, farBoost: 1.35
  },
  "focus-word": {
    charsPerLine: 1, sizeBoost: 2.5, depthStep: 0, arrival: "charge",
    overshoot: 0.12, spin: 0.0, farBoost: 1.6
  },
  "cascade": {
    charsPerLine: 9, sizeBoost: 0.9, depthStep: 3.4, arrival: "fall",
    overshoot: 0.0, spin: 0.06, farBoost: 1.0
  },
  "wipe-fill": {
    charsPerLine: 20, sizeBoost: 0.95, depthStep: 0, arrival: "present",
    overshoot: 0.0, spin: 0.0, farBoost: 0.8
  },
  "bold-stack": {
    charsPerLine: 11, sizeBoost: 1.15, depthStep: 5.0, arrival: "punch",
    overshoot: 0.22, spin: 0.0, farBoost: 1.1
  },
  "minimal": {
    charsPerLine: 26, sizeBoost: 0.55, depthStep: 0, arrival: "fade",
    overshoot: 0.0, spin: 0.0, farBoost: 0.55
  }
};

const personalityFor = spec => PERSONALITY[spec && spec.id] || PERSONALITY["kinetic-slam"];

/* ---------------------------------------------------------------- scene -- */

class Odyssey {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.camera = new THREE.PerspectiveCamera(62, 16 / 9, 0.5, 900);
    this.kit = null;
    this.scene = null;
    this.textLayer = new THREE.Group();
    this.textMeshes = new Map();
    this.lyricLayouts = new Map();
    this.environment = null;
  }

  /**
   * A bare scene holding nothing but the lyric, drawn over whichever 2D
   * background is active. This is what lets 3D text work everywhere instead of
   * being welded to the Odyssey corridor.
   */
  buildTextOnly() {
    if (this.kit === "__text__") return;
    this.disposeScene();
    this.kit = "__text__";
    this.theme = null;
    const scene = new THREE.Scene();
    scene.background = null;
    scene.add(new THREE.AmbientLight(0xffffff, 1));
    this.sky = null;
    this.ridges = null;
    this.ground = null;
    this.laneGroup = null;
    this.slots = [];
    this.travelLight = null;
    this.ambientLight = null;
    this.keyLight = null;
    this.rimLight = null;
    this.environment = null;
    this.waveField = makeWaveField(0x4de2ff);
    this.waveField.visible = false;
    scene.add(this.waveField);
    this.textMeshes.clear();
    this.textLayer = new THREE.Group();
    this.scene = scene;
  }

  build(kitName) {
    if (this.kit === kitName) return;
    this.disposeScene();
    this.kit = kitName;
    const theme = { ...(THEMES[kitName] || THEMES.japan), kit: kitName };
    this.theme = theme;

    if (kitName === "ocean") {
      this.scene = new THREE.Scene();
      this.scene.add(new THREE.AmbientLight(0xe2ecff, 1.4));
      const key = new THREE.DirectionalLight(0xffffff, 2);
      key.position.set(-3, 8, 4); this.scene.add(key);
      this.ocean = createOcean(THREE); this.scene.add(this.ocean.group);
      this.slots = []; this.sky = null; this.ridges = null; this.ground = null;
      this.waveField = null; this.environment = null; this.expeditions = null;
      this.textMeshes.clear(); this.textLayer = new THREE.Group();
      return;
    }

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(theme.fog, 26, 250);
    scene.background = new THREE.Color(theme.fog);

    this.sky = makeSky(theme);
    scene.add(this.sky);
    this.ridges = makeRidges(theme);
    scene.add(this.ridges);

    this.ambientLight = new THREE.AmbientLight(theme.cool, 0.55);
    scene.add(this.ambientLight);
    const key = new THREE.DirectionalLight(theme.key, 1.15);
    key.position.set(-6, 14, -10);
    scene.add(key);
    this.keyLight = key;
    const rim = new THREE.DirectionalLight(theme.moon, 0.7);
    rim.position.set(9, 6, 14);
    scene.add(rim);
    this.rimLight = rim;
    this.travelLight = new THREE.PointLight(theme.warm, 26, 60, 2);
    scene.add(this.travelLight);

    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(700, 1400),
      new THREE.MeshStandardMaterial({ color: theme.ground, roughness: 0.35, metalness: 0.55 })
    );
    ground.rotation.x = -Math.PI / 2;
    scene.add(ground);
    this.ground = ground;
    this.environment = createEnvironment(THREE, theme);
    scene.add(this.environment.group);
    this.world = createWorld(THREE, theme);
    this.landmarkStyle = null;
    scene.add(this.world.group);
    this.expeditions = createExpeditions(THREE);
    scene.add(this.expeditions.group);

    // Emissive centre line: cheap, and it reads as the road pulling you forward.
    this.laneGroup = new THREE.Group();
    const laneMaterial = new THREE.MeshBasicMaterial({ color: theme.key, transparent: true, opacity: 0.5 });
    for (let i = 0; i < 60; i += 1) {
      const dash = new THREE.Mesh(new THREE.PlaneGeometry(0.35, 3.4), laneMaterial);
      dash.rotation.x = -Math.PI / 2;
      dash.position.y = 0.02;
      this.laneGroup.add(dash);
    }
    scene.add(this.laneGroup);

    this.waveField = makeWaveField(0x4de2ff);
    this.waveField.visible = false;
    scene.add(this.waveField);

    const materials = makeMaterials(theme);
    this.slots = [];
    for (let i = 0; i < VISIBLE_SLOTS; i += 1) {
      const holder = new THREE.Group();
      const terrace = new THREE.Mesh(new THREE.IcosahedronGeometry(1, 1), materials.stone);
      terrace.position.y = -1.1;
      terrace.scale.set(4.3, 1.2, 3.5);
      terrace.visible = false;
      holder.add(terrace);
      holder.userData.terrace = terrace;
      holder.userData.variants = [];
      for (let v = 0; v < PROTOTYPES_PER_SLOT; v += 1) {
        const choices = kitName === "usa" ? ["billboard", "pole", "dinerSign", "pole"] : theme.builders;
        const builder = BUILDERS[choices[v % choices.length]];
        const variant = builder(materials, theme);
        variant.visible = false;
        holder.add(variant);
        holder.userData.variants.push(variant);
      }
      scene.add(holder);
      this.slots.push(holder);
    }

    this.scene = scene;
    // Lyrics are planted in world space on the first setLyric call.
    this.textMeshes.clear();
    this.textLayer = new THREE.Group();
    // Compile on first render. Async polling can outlive a kit switch and
    // dereference programs already disposed with the previous scene.
  }

  /** Compose the world for playback second `t`. Pure: no state carries over. */
  update(t, options = {}) {
    const {
      direction = "forward", seed = 1337, speed = 9, pulse = 0, density = 1,
      artStyle = "cinematic", secondaryMotion = "none", motionAmount = 0.35,
      wave = false, waveColor = "#4de2ff", waveIntensity = 1, spectrum = null,
      environment = { weather: "clear", daytime: "sunset", season: "summer" }
    } = options;
    const dir = DIRECTIONS[direction] || DIRECTIONS.forward;
    const travel = t * speed;

    if (this.ocean) {
      updateOceanCamera(this.camera, t, options);
      updateOcean(THREE, this.ocean, { ...options, t, camera: this.camera });
      return this;
    }

    if (!this.slots || !this.slots.length) {
      // Text-only scene: just fly the camera so planted words still stream past.
      this.camera.position.set(0, 3.4, -travel);
      this.camera.rotation.set(0, 0, 0);
      if (this.waveField) {
        this.waveField.visible = Boolean(wave);
        if (wave) {
          updateWaveField(this.waveField, t, this.camera.position.z, spectrum,
            waveColor, waveIntensity, pulse);
        }
      }
      return this;
    }

    const camY = 3.4 + dir.rise * Math.sin(t * 0.21) * 3.2;
    const camX = dir.sway ? Math.sin(t * 0.24) * dir.sway : 0;
    this.camera.position.set(camX, Math.max(1.2, camY), -travel);
    this.camera.rotation.set(dir.look, 0, dir.roll ? Math.sin(t * 0.19) * dir.roll : 0);

    this.sky.position.copy(this.camera.position);
    for (const ridge of this.ridges.children) {
      ridge.position.x = camX - travel * ridge.userData.parallax;
      ridge.position.y = 8;
      ridge.position.z = this.camera.position.z - 240 - ridge.userData.depth;
    }
    this.ground.position.z = this.camera.position.z;
    this.travelLight.position.set(camX, 6, this.camera.position.z - 16);
    this.travelLight.intensity = 24 + pulse * 26;

    const firstSlot = Math.floor(travel / SLOT);
    for (let i = 0; i < this.slots.length; i += 1) {
      const holder = this.slots[i];
      const slotIndex = firstSlot + i;
      const random = rng(slotIndex * 2654435761 + seed);

      const populated = random() < 0.35 + 0.5 * density;
      const variantIndex = Math.floor(random() * PROTOTYPES_PER_SLOT);
      const side = slotIndex % 2 === 0 ? -1 : 1;
      const scale = 0.85 + random() * .25;
      // Push bigger props further out and keep a clear corridor down the middle.
      // The old band was 5-13 units wide, so neighbouring slots overlapped each
      // other and crowded the road.
      const lateral = side * (this.kit === 'usa' ? 9 : this.kit === 'italy' ? 16 : 14);
      const spin = 0;
      // Depth jitter stops the props lining up as a wall every SLOT units.
      const z = -(slotIndex * SLOT) - (this.kit === 'usa' ? 12 : 0);

      for (let v = 0; v < holder.userData.variants.length; v += 1) {
        holder.userData.variants[v].visible = populated && v === variantIndex;
      }
      holder.position.set(...sceneryPoint(lateral, 0, z, travel, direction, this.camera.position.z));
      const secondaryAmount = clamp(Number(motionAmount) || 0);
      if (secondaryMotion === 'sway') holder.position.x += Math.sin(t * .19) * secondaryAmount * 5;
      if (secondaryMotion === 'rise') holder.position.y += Math.sin(t * .14) * secondaryAmount * 4;
      if (secondaryMotion === 'orbit') {
        const angle = Math.sin(t * .12) * secondaryAmount * .12;
        const x = holder.position.x, y = holder.position.y;
        holder.position.x = x * Math.cos(angle) - y * Math.sin(angle);
        holder.position.y = x * Math.sin(angle) + y * Math.cos(angle);
      }
      holder.userData.terrace.visible = populated && ['up', 'down', 'ascend', 'dive'].includes(direction);
      holder.rotation.y = spin + (direction === 'left' ? -Math.PI / 2 : direction === 'right' ? Math.PI / 2 : 0);
      holder.scale.setScalar(scale);
    }

    if (this.waveField) {
      this.waveField.visible = Boolean(wave);
      if (wave) {
        updateWaveField(this.waveField, t, this.camera.position.z, spectrum,
          waveColor, waveIntensity, pulse);
      }
    }

    updateEnvironment(THREE, this.environment, {
      scene: this.scene, sky: this.sky, ground: this.ground, camera: this.camera.position,
      ambient: this.ambientLight, key: this.keyLight, rim: this.rimLight,
      travelLight: this.travelLight, t, state: environment
    });
    updateWorld(THREE, this.world, { t, travel, direction, cameraZ: this.camera.position.z,
      seed, artStyle, density, secondaryMotion, motionAmount, kitName: this.kit });
    if (this.landmarkStyle !== artStyle) {
      this.landmarkStyle = artStyle;
      const materials = new Set();
      for (const holder of this.slots) holder.traverse(object => {
        if (object.isMesh && object.material?.color) materials.add(object.material);
      });
      for (const material of materials) {
        if (!material.userData.originalPalette) material.userData.originalPalette = {
          color: material.color.clone(), emissive: material.emissive?.clone(),
          intensity: material.emissiveIntensity, map: material.map
        };
        const original = material.userData.originalPalette;
        material.color.copy(original.color);
        if (material.emissive && original.emissive) material.emissive.copy(original.emissive);
        material.emissiveIntensity = original.intensity;
        material.map = original.map;
        if (artStyle === 'storybook') {
          material.color.lerp(new THREE.Color(0xa39675), .46);
          material.emissiveIntensity *= .16;
          material.map = this.world.paperTexture;
        }
        material.needsUpdate = true;
      }
    }
    const vertical = ['up', 'down', 'ascend', 'dive'].includes(direction);
    for(const holder of this.slots)holder.visible=!vertical;
    this.world.group.visible=!vertical;
    updateExpeditions(THREE,this.expeditions,{t,travel,cameraZ:this.camera.position.z,direction,seed,artStyle});
    // Secondary movement is applied in the newly chosen world's local frame.
    this.expeditions.group.position.copy(this.world.group.position);
    this.expeditions.group.rotation.copy(this.world.group.rotation);
    const underground=direction==='down'||direction==='dive';
    this.sky.visible=!underground;this.ridges.visible=!vertical && this.kit !== 'usa';
    if(underground){
      this.scene.background.set(0x09131c);this.scene.fog.color.set(0x09131c);
      this.scene.fog.near=30;this.scene.fog.far=190;
      this.ambientLight.color.set(0xc0c8c7);this.ambientLight.intensity=1.1;
      this.keyLight.color.set(0x90c4ca);this.keyLight.intensity=1.4;
      this.travelLight.color.set(0x60e8d6);this.travelLight.intensity=55;
    }else this.travelLight.color.set(this.theme.warm);
    this.ground.visible = !vertical;
    if(!vertical)this.ground.material.color.set(this.world.groundColor ?? this.theme.ground);
    // The river and banks carry perspective; a neon dashed road flattened it.
    this.laneGroup.visible = false;
    if (artStyle === 'storybook') {
      this.ambientLight.intensity = Math.max(.9, this.ambientLight.intensity);
      this.ground.material.roughness = .95;
      this.ground.material.metalness = 0;
    } else {
      this.ground.material.roughness = .55;
      this.ground.material.metalness = .2;
    }

    // Lane dashes recycle around the camera so the road never runs out.
    const dashSpacing = 7;
    const dashPhase = travel % dashSpacing;
    for (let i = 0; i < this.laneGroup.children.length; i += 1) {
      const dash = this.laneGroup.children[i];
      dash.position.set(camX * 0.2, 0.02, this.camera.position.z - (i * dashSpacing - dashPhase) - 4);
    }

    return this;
  }

  /**
   * Place the lyric inside the world.
   *
    * Phrases are anchored in world space so the moving camera reaches and then
    * passes them. Recomputing their Z from the current camera position tethered
    * them to the viewer and made the travel stop halfway through.
   * Timing comes from the caller, which already owns the kinetic clock, so 3D
   * text stays sample-accurate with the rest of the app.
   */
  /**
   * Layout for one phrase, computed once and cached.
   *
   * Recomputing this per frame from whichever words happened to be visible was
   * what made the lyric jump: a word appearing changed the line count, which
   * changed the fitted size, which moved every other word. The layout now
   * depends only on the phrase and the style, so it is stable for the whole cue.
   */
  layoutFor(cue, style, speed, spec) {
    const person = personalityFor(spec);
    const key = [
      cue.id, spec && spec.id, style.fontSize, style.maxWidth,
      style.font, this.camera.aspect.toFixed(3),
      cue.entries.map(entry => `${entry.key}:${entry.text}`).join("\u001f")
    ].join("|");
    const cached = this.lyricLayouts.get(key);
    if (cached) return cached;

    const refDistance = 16;
    const viewH = 2 * refDistance * Math.tan((this.camera.fov * Math.PI) / 360);
    const viewW = viewH * this.camera.aspect;
    const shortView = Math.min(viewH, viewW);

    // Break lines for the size the BOARD will actually be. Inheriting the flat
    // engine's break points meant every phrase arrived as one long line that
    // was then shrunk to fit, which is why nothing ever wrapped.
    //
    // The words come from the entries: `cue` here is assembled from them and
    // carries no text of its own.
    const words = cue.entries
      .map(entry => ({ text: entry.text, key: entry.key, index: entry.wordIndex ?? 0 }))
      .sort((a, b) => a.index - b.index);
    const wrapped = [];
    let line = [];
    let width = 0;
    for (const word of words) {
      const cost = word.text.length + 1;
      if (line.length && (width + cost > person.charsPerLine || person.charsPerLine <= 1)) {
        wrapped.push(line); line = []; width = 0;
      }
      line.push(word);
      width += cost;
    }
    if (line.length) wrapped.push(line);
    const spatialFocus = spec?.id === "spiral" || spec?.id === "constellation";
    const lineCount = spatialFocus ? 1 : Math.max(1, wrapped.length);

    let unit = shortView * (style.fontSize / 1080) * 2.6 * person.sizeBoost;
    let widest = 0;
    for (const row of wrapped) {
      let span = 0;
      for (const word of row) span += wordTexture(word.text, style).aspect * 0.68 + 0.26;
      widest = Math.max(widest, span - 0.26);
    }
    const growth = Math.pow(BOARD_NEAR / refDistance, 0.72) * (refDistance / BOARD_NEAR);
    const widthBudget = viewW * (style.maxWidth ?? 88) / 100 / Math.max(1, growth);
    if (widest * unit > widthBudget) unit = widthBudget / widest;

    const blockUnits = (lineCount - 1) * 1.16 + 1.05;
    const heightBudget = viewH * 0.7 / Math.max(1, growth);
    if (blockUnits * unit > heightBudget) unit = heightBudget / blockUnits;

    const gap = unit * 0.26;
    const slots = new Map();
    wrapped.forEach((row, lineIndex) => {
      let total = 0;
      const widths = row.map(word => {
        const w = unit * wordTexture(word.text, style).aspect * 0.68;
        total += w + gap;
        return w;
      });
      total -= gap;
      let cursor = -total / 2;
      row.forEach((word, i) => {
        slots.set(word.key, {
          x: cursor + widths[i] / 2,
          y: spatialFocus ? 0 : (lineCount - 1) * unit * 0.58 - lineIndex * unit * 1.16,
          // Lines can sit at different depths, which is what gives Cascade and
          // Bold Stack a shape you can read as 3D rather than as a flat card.
          z: spatialFocus ? 0 : -lineIndex * person.depthStep,
          line: lineIndex
        });
        cursor += widths[i] + gap;
      });
    });

    const blockHeight = blockUnits * unit;
    const layout = {
      unit, slots, blockHalf: blockHeight / 2,
      readDistance: refDistance, person
    };
    this.lyricLayouts.set(key, layout);
    if (this.lyricLayouts.size > 64) {
      this.lyricLayouts.delete(this.lyricLayouts.keys().next().value);
    }
    return layout;
  }

  /**
   * Plant each phrase in the world and let the corridor carry it.
   *
   * The board is born deep down the corridor and travels toward the viewer at
   * exactly the speed of the scenery, so the lyric arrives the same way the
   * torii and the lanterns do. Words light up in place on the board as they are
   * sung, sliding forward out of the board's own depth.
   */
  setLyric(entries, style, t, world = {}) {
    const spec = world.spec || null;
    if (!this.scene) return;
    if (this.textLayer.parent !== this.scene) this.scene.add(this.textLayer);
    if (!this.lyricLayouts) this.lyricLayouts = new Map();

    const speed = world.speed || 9;
    const cam = this.camera.position;
    // One rigid rotation for the whole phrase, not independent letter tilts.
    // Defaults preserve old projects. Reuse scratch objects across every word.
    const radians = (value, limit) => THREE.MathUtils.degToRad(clamp(Number(value) || 0, -limit, limit));
    const orientation = this.lyricOrientation ||= new THREE.Quaternion();
    const localRotation = this.lyricLocalRotation ||= new THREE.Quaternion();
    const euler = this.lyricEuler ||= new THREE.Euler();
    const point = this.lyricPoint ||= new THREE.Vector3();
    orientation.setFromEuler(euler.set(radians(style.text3DPitch, 85), radians(style.text3DYaw, 85), radians(style.text3DRoll, 180)));
    // Building a whole phrase of slabs in one frame is what caused the hitch
    // on every phrase change; spread the work across frames instead.
    let meshBudget = 4;

    const wanted = new Set(entries.map(entry => entry.key));
    for (const [key, mesh] of [...this.textMeshes]) {
      if (!wanted.has(key)) {
        this.textLayer.remove(mesh);
        this.textMeshes.delete(key);
      }
    }

    const cues = new Map();
    for (const entry of entries) {
      let cue = cues.get(entry.cueId);
      if (!cue) {
        cue = { id: entry.cueId, start: entry.cueStart, end: entry.cueEnd, entries: [] };
        cues.set(entry.cueId, cue);
      }
      cue.entries.push(entry);
    }

    for (const cue of cues.values()) {
      const layout = this.layoutFor(cue, style, speed, spec);
      // The phrase is fixed at the point the camera will reach near cue.end.
      // This produces one continuous, linear world-space flight at every speed.
      const boardZ = window.VFScene.lyricBoardZ(cue.end, speed, BOARD_NEAR);
      const distance = window.VFScene.lyricBoardDistance(cue.end, t, speed, BOARD_NEAR);

      for (const entry of cue.entries) {
        const slot = layout.slots.get(entry.key);
        if (!slot) continue;
        let mesh = this.textMeshes.get(entry.key);
        const meshSignature = [
          entry.text, style.font, style.color, style.accent, style.stroke,
          style.strokeWidth, layout.unit.toFixed(5)
        ].join("|");
        if (mesh && mesh.userData.signature !== meshSignature) {
          this.textLayer.remove(mesh);
          this.textMeshes.delete(entry.key);
          mesh = null;
        }
        if (!mesh) {
          if (meshBudget <= 0) continue;
          meshBudget -= 1;
          mesh = buildWordSlab(entry.text, style, layout.unit);
          mesh.userData.signature = meshSignature;
          this.textLayer.add(mesh);
          this.textMeshes.set(entry.key, mesh);
        }

        // Hide only once the board is genuinely behind the viewer.
        if (distance < 1.2) { mesh.visible = false; continue; }

        const hash = hashKey(entry.key);
        const person = layout.person;
        const flight = clamp(entry.arrive);
        const eased = 1 - Math.pow(1 - flight, 3);
        const back = 1 - eased;

        // A real scene object: fixed world size, centred on the corridor and
        // resting on the ground. Camera sway and travel now create the parallax;
        // no X/Y/Z component follows or compensates for the camera.
        const steady = 1;
        const groundClearance = 0.32;
        let x = slot.x + Number(style.offset3DX || 0);
        let y = groundClearance + slot.y + layout.blockHalf + Number(style.offset3DY || 0);
        let z = boardZ + slot.z;
        let yaw = 0;
        let pitch = 0;
        let scaleBoost = 1;

        // Each personality arrives its own way. Previously every preset used
        // the same randomly chosen direction, so switching style changed
        // nothing you could see.
        const depth = 44 * person.farBoost;
        if (person.arrival === "spiral") {
          const p=clamp((t-entry.wordStart)/.55), radius=(1-p)*12, angle=(1-p)*Math.PI*4;
          x += Math.cos(angle)*radius; y += Math.sin(angle)*radius; z -= (1-p)*45;
          scaleBoost = .4+.6*p; yaw = Math.sin(angle)*.2;
        } else if (person.arrival === "scatter") {
          const phase=(entry.wordIndex+1)*2.399963+cue.start*.17;
          const other=entry.state.role !== "active";
          if (other) { x += Math.cos(phase)*17; y += Math.sin(phase)*8; z -= 10+(entry.wordIndex%4)*9; scaleBoost=.4; }
          else { x=Number(style.offset3DX)||0; y=groundClearance+layout.blockHalf+Number(style.offset3DY||0); z=boardZ; }
        } else if (person.arrival === "punch") {
          z -= back * depth;
          scaleBoost = 1 + person.overshoot * back;
          yaw = clampAngle(((hash >> 8) % 100 / 100 - 0.5) * 0.5 * back, 0.3);
        } else if (person.arrival === "drift") {
          z -= back * depth;
          x += (((hash >> 4) % 2) ? 1 : -1) * back * 14;
          yaw = clampAngle(back * person.spin * 4, 0.3);
        } else if (person.arrival === "charge") {
          z -= back * depth * 1.5;
          scaleBoost = 1 + person.overshoot * back;
        } else if (person.arrival === "fall") {
          y += back * layout.unit * 3.2 * steady;
          z -= back * depth * 0.55;
          pitch = clampAngle(back * 0.34, 0.14);
        } else if (person.arrival === "present") {
          z -= back * 4;
        } else {
          z -= back * depth * 0.4;
        }

        mesh.visible = true;
        const anchorX = Number(style.offset3DX) || 0;
        const anchorY = groundClearance + layout.blockHalf + (Number(style.offset3DY) || 0);
        point.set(x - anchorX, y - anchorY, z - boardZ).applyQuaternion(orientation);
        mesh.position.set(anchorX + point.x, anchorY + point.y, boardZ + point.z);
        localRotation.setFromEuler(euler.set(pitch, yaw, 0));
        mesh.quaternion.copy(orientation).multiply(localRotation);
        mesh.scale.setScalar(layout.unit * steady * scaleBoost);

        // One smooth curve from birth to fly-past: no separate exit, which is
        // where the old snap came from.
        // Dissolve while it is still sweeping past rather than letting it
        // fill the frame on the way out.
        const near = clamp((distance - 1.2) / 7);
        // One curve, not two. Multiplying the kinetic reveal by the flight
        // easing made the pair reach full opacity well before the syllable; the
        // flight now only moves the word, and the engine alone decides when it
        // is visible.
        const opacity = clamp(entry.state.opacity) * near;
        for (const layer of mesh.children) {
          layer.material.opacity = opacity * layer.userData.alpha;
          const map = entry.state.fill > 0.5 ? layer.userData.accentMap : layer.userData.baseMap;
          if (layer.userData.face && layer.material.map !== map) {
            layer.material.map = map;
            layer.material.needsUpdate = true;
          }
        }
      }
    }
  }

  clearLyric() {
    for (const [, mesh] of this.textMeshes) mesh.visible = false;
  }

  disposeScene() {
    if (!this.scene) return;
    const geometries = new Set(), materials = new Set(), textures = new Set();
    this.scene.traverse(object => {
      for (const texture of object.userData.ownedTextures || []) textures.add(texture);
      if (object.geometry) geometries.add(object.geometry);
      const list = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of list) if (material) {
        materials.add(material);
        for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
      }
    });
    for (const texture of textures) texture.dispose();
    for (const geometry of geometries) geometry.dispose();
    for (const material of materials) material.dispose();
    textureCache.clear();
    this.lyricLayouts.clear();
    this.world = null;
    this.ocean = null;
  }

  setSize(width, height) {
    if (this.canvas.width === width && this.canvas.height === height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / Math.max(1, height);
    this.camera.updateProjectionMatrix();
  }

  render() {
    if (this.scene) this.renderer.render(this.scene, this.camera);
  }
}

const instances = new WeakMap();

window.VFSceneGL = {
  THREE,
  THEMES,
  DIRECTIONS,
  ready: true,
  get(canvas) {
    if (!instances.has(canvas)) instances.set(canvas, new Odyssey(canvas));
    return instances.get(canvas);
  }
};
window.dispatchEvent(new Event("vfscenegl-ready"));
