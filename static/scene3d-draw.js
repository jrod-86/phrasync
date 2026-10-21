/*
 * Canvas painter for the KaraokeSesh 3D corridor.
 *
 * Consumes VFScene.sample() and rasterises it for the live preview.
 */
(() => {
  "use strict";

  const S = () => window.VFScene;

  function hex(value) {
    const raw = String(value || "").replace("#", "");
    const full = raw.length === 3 ? raw.split("").map(c => c + c).join("") : raw;
    return [
      parseInt(full.slice(0, 2), 16) || 0,
      parseInt(full.slice(2, 4), 16) || 0,
      parseInt(full.slice(4, 6), 16) || 0
    ];
  }

  const rgba = (rgb, alpha) => `rgba(${rgb[0]|0},${rgb[1]|0},${rgb[2]|0},${alpha})`;

  function towards(rgb, target, amount) {
    return [
      rgb[0] + (target[0] - rgb[0]) * amount,
      rgb[1] + (target[1] - rgb[1]) * amount,
      rgb[2] + (target[2] - rgb[2]) * amount
    ];
  }

  /** Stars, a moon or sun, and parallax ridges above the horizon. */
  function paintSky(ctx, width, height, theme, scene, pulse) {
    const scene3d = S();
    const horizon = height / 2;
    const body = theme.celestial;
    const ridge = theme.skyline;

    // Stars, seeded so they hold still while the ridges scroll past them.
    if (body && body.kind === "moon") {
      const random = scene3d.rng(9001);
      ctx.fillStyle = "rgba(255,255,255,.75)";
      for (let i = 0; i < 90; i += 1) {
        const x = random() * width;
        const y = random() * horizon * 0.92;
        const r = random() * 1.5 + 0.3;
        ctx.globalAlpha = 0.15 + random() * 0.55;
        ctx.fillRect(x, y, r, r);
      }
      ctx.globalAlpha = 1;
    }

    if (body) {
      const cx = body.x * width;
      const cy = body.y * horizon;
      const r = body.r * height;
      const halo = ctx.createRadialGradient(cx, cy, r * 0.6, cx, cy, r * (4.2 + pulse));
      halo.addColorStop(0, rgba(hex(body.halo), 0.34));
      halo.addColorStop(1, rgba(hex(body.halo), 0));
      ctx.fillStyle = halo;
      ctx.fillRect(0, 0, width, horizon + r * 2);
      ctx.fillStyle = body.color;
      ctx.beginPath();
      ctx.arc(cx, cy, r, 0, Math.PI * 2);
      ctx.fill();
    }

    if (!ridge) return;
    for (let layer = 0; layer < ridge.layers; layer += 1) {
      const depth = layer / Math.max(1, ridge.layers - 1);
      // Nearer layers scroll faster, which is what sells the distance.
      const parallax = scene.travel * (0.0016 + layer * 0.0032);
      const profile = scene3d.ridgeProfile(4200 + layer * 31, ridge.kind === "city" ? 28 : 14);
      const amp = height * ridge.amp * (0.55 + depth * 0.75);
      const baseY = horizon + 2 - layer * height * 0.012;

      ctx.fillStyle = ridge.colors[Math.min(layer, ridge.colors.length - 1)];
      ctx.beginPath();
      ctx.moveTo(0, baseY);
      const steps = ridge.kind === "city" ? 56 : 96;
      for (let i = 0; i <= steps; i += 1) {
        const u = i / steps;
        const x = u * width;
        let n = scene3d.sampleProfile(profile, u * 1.6 + parallax);
        if (ridge.kind === "city") n = Math.round(n * 5) / 5;      // blocky rooftops
        else if (ridge.kind === "hills") n = Math.pow(n, 1.5);      // soft swells
        else n = Math.pow(n, 0.72);                                 // sharp peaks
        const y = baseY - n * amp;
        if (ridge.kind === "city") {
          ctx.lineTo(x, y);
          ctx.lineTo(x + width / steps, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.lineTo(width, baseY);
      ctx.closePath();
      ctx.fill();
    }
  }

  /** Sky, horizon haze and the ground plane the props stand on. */
  function paintBackdrop(ctx, width, height, theme, scene, pulse) {
    const horizon = height / 2;
    const sky = ctx.createLinearGradient(0, 0, 0, horizon);
    sky.addColorStop(0, theme.sky[0]);
    sky.addColorStop(0.62, theme.sky[1]);
    sky.addColorStop(1, theme.sky[2]);
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, width, horizon + 2);
    paintSky(ctx, width, height, theme, scene, pulse);

    // Wet-asphalt floor: the sky colour bleeds down as a reflection and lifts
    // again toward the camera, so the lower third is never a dead black band.
    const accentRgb = hex(theme.palette[2]);
    const ground = ctx.createLinearGradient(0, horizon, 0, height);
    ground.addColorStop(0, theme.sky[2]);
    ground.addColorStop(0.14, theme.ground);
    ground.addColorStop(0.62, theme.ground);
    ground.addColorStop(1, rgba(towards(hex(theme.ground), accentRgb, 0.30), 1));
    ctx.fillStyle = ground;
    ctx.fillRect(0, horizon - 1, width, height - horizon + 1);

    // Mirrored smear of the horizon glow, the cue that the floor is reflective.
    const mirror = ctx.createLinearGradient(0, horizon, 0, height * 0.86);
    mirror.addColorStop(0, rgba(accentRgb, 0.30 + pulse * 0.14));
    mirror.addColorStop(0.45, rgba(accentRgb, 0.07));
    mirror.addColorStop(1, rgba(accentRgb, 0));
    ctx.fillStyle = mirror;
    ctx.fillRect(0, horizon, width, height - horizon);

    // A soft bloom on the vanishing point sells the "coming out of the dark".
    const bloom = ctx.createRadialGradient(width / 2, horizon, 0, width / 2, horizon, height * (0.42 + pulse * 0.1));
    const accent = hex(theme.palette[2]);
    bloom.addColorStop(0, rgba(accent, 0.17 + pulse * 0.13));
    bloom.addColorStop(1, rgba(accent, 0));
    ctx.fillStyle = bloom;
    ctx.fillRect(0, 0, width, height);

    // Perspective floor lines, recycled with the camera so they never drift.
    const scene3d = S();
    const spacing = scene3d.SLOT / 2;
    const phase = scene.travel % spacing;
    for (let i = 1; i < 30; i += 1) {
      const z = i * spacing - phase;
      if (z < scene3d.NEAR) continue;
      const p = scene3d.project(0, -scene.camY, z, width, height, scene.roll);
      if (p.y <= horizon || p.y > height) continue;
      const nearness = scene3d.clamp((p.y - horizon) / (height - horizon));
      ctx.strokeStyle = rgba(accentRgb, 0.06 + nearness * 0.34);
      ctx.lineWidth = Math.max(1, (height / 900) * (1 + nearness * 2.4));
      ctx.beginPath();
      ctx.moveTo(0, p.y);
      ctx.lineTo(width, p.y);
      ctx.stroke();
    }
    ctx.strokeStyle = rgba(accentRgb, 0.13);
    ctx.lineWidth = Math.max(1, height / 780);
    ctx.beginPath();
    for (let lane = -6; lane <= 6; lane += 1) {
      const near = scene3d.project(lane * 3 - scene.camX, -scene.camY, scene3d.NEAR + 1.2, width, height, scene.roll);
      const far = scene3d.project(lane * 3 - scene.camX, -scene.camY, 70, width, height, scene.roll);
      ctx.moveTo(near.x, near.y);
      ctx.lineTo(far.x, far.y);
    }
    ctx.stroke();
  }

  function paintProp(ctx, item, theme, width, height, pulse) {
    const scene3d = S();
    const alpha = scene3d.depthAlpha(item.z);
    if (alpha <= 0.02) return;

    const base = scene3d.project(item.x, item.y + item.bob, item.z, width, height, item.roll);
    const unit = base.f * item.scale;
    if (unit < 0.4) return;

    const fog = hex(theme.sky[1]);
    const lift = item.lit ? 1 + pulse * 0.5 : 1;

    const colour = index => {
      const rgb = towards(hex(theme.palette[index]), fog, 1 - alpha);
      return index >= 2 ? rgb.map(c => Math.min(255, c * lift)) : rgb;
    };
    const put = (lx, ly) => [base.x + lx * unit, base.y - ly * unit];

    ctx.save();
    ctx.globalAlpha = alpha;
    for (const part of item.prop.parts) {
      const kind = part[0];
      if (kind === "rect") {
        const [, lx, ly, w, h, ci] = part;
        const [x, y] = put(lx, ly + h);
        ctx.fillStyle = rgba(colour(ci), 1);
        ctx.fillRect(x, y, Math.max(1, w * unit), Math.max(1, h * unit));
      } else if (kind === "tri") {
        const [, x1, y1, x2, y2, x3, y3, ci] = part;
        const a = put(x1, y1), b = put(x2, y2), c = put(x3, y3);
        ctx.fillStyle = rgba(colour(ci), 1);
        ctx.beginPath();
        ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.lineTo(c[0], c[1]);
        ctx.closePath(); ctx.fill();
      } else if (kind === "ellipse") {
        const [, cx, cy, rx, ry, ci] = part;
        const [x, y] = put(cx, cy);
        ctx.fillStyle = rgba(colour(ci), 1);
        ctx.beginPath();
        ctx.ellipse(x, y, Math.max(0.5, rx * unit), Math.max(0.5, ry * unit), 0, 0, Math.PI * 2);
        ctx.fill();
      } else if (kind === "ring") {
        const [, cx, cy, r, thickness, ci] = part;
        const [x, y] = put(cx, cy);
        ctx.strokeStyle = rgba(colour(ci), 1);
        ctx.lineWidth = Math.max(1, thickness * unit);
        ctx.beginPath();
        ctx.arc(x, y, Math.max(1, r * unit), 0, Math.PI * 2);
        ctx.stroke();
      } else if (kind === "glow") {
        const [, cx, cy, r, ci] = part;
        const [x, y] = put(cx, cy);
        const radius = Math.max(2, r * unit * (1 + pulse * 0.35));
        const grad = ctx.createRadialGradient(x, y, 0, x, y, radius);
        const rgb = colour(ci);
        grad.addColorStop(0, rgba(rgb, 0.55 * alpha));
        grad.addColorStop(1, rgba(rgb, 0));
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(x, y, radius, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.restore();
  }

  /** Paint one frame of the corridor into ctx. */
  function paint(ctx, width, height, options) {
    const scene3d = S();
    const scene = scene3d.sample(options);
    const { theme, items, pulse } = scene;

    paintBackdrop(ctx, width, height, theme, scene, pulse);
    for (const item of items) paintProp(ctx, item, theme, width, height, pulse);

    // Distance haze pulled over everything, densest at the horizon.
    const haze = ctx.createLinearGradient(0, height * 0.30, 0, height * 0.62);
    const fog = hex(theme.sky[1]);
    haze.addColorStop(0, rgba(fog, 0));
    haze.addColorStop(0.55, rgba(fog, 0.42));
    haze.addColorStop(1, rgba(fog, 0));
    ctx.fillStyle = haze;
    ctx.fillRect(0, 0, width, height);

    // Vignette keeps the lyric readable against a busy corridor.
    const vignette = ctx.createRadialGradient(
      width / 2, height / 2, Math.min(width, height) * 0.26,
      width / 2, height / 2, Math.max(width, height) * 0.76
    );
    vignette.addColorStop(0, "rgba(0,0,0,0)");
    vignette.addColorStop(1, "rgba(0,0,0,.62)");
    ctx.fillStyle = vignette;
    ctx.fillRect(0, 0, width, height);
  }

  window.VFSceneDraw = { paint, hex, rgba, towards };
})();
