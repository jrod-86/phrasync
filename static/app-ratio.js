"use strict";

// Canvas aspect ratio. "original" follows the first picture or video in the
// project (the background, else the first footage clip); the Ratio button on
// the preview picks an exact ratio instead.

const ASPECT_RATIOS = [
  { value: "original", label: "Original", hint: "Match your picture or video" },
  { value: "16:9", label: "16:9", hint: "YouTube, landscape" },
  { value: "9:16", label: "9:16", hint: "TikTok, Shorts, Reels" },
  { value: "1:1", label: "1:1", hint: "Square" },
  { value: "4:5", label: "4:5", hint: "Instagram portrait" },
  { value: "4:3", label: "4:3", hint: "Classic TV" },
  { value: "3:4", label: "3:4", hint: "Portrait" },
  { value: "2:1", label: "2:1", hint: "Wide" },
  { value: "21:9", label: "21:9", hint: "Ultrawide" },
  { value: "2.35:1", label: "2.35:1", hint: "Cinema" },
  { value: "1.85:1", label: "1.85:1", hint: "Film" }
];

let originalRatio = 16 / 9;
let originalSource = "";

function aspectRatioValue(aspect) {
  if (aspect === "original") return originalRatio;
  const [w, h] = String(aspect || "16:9").split(":").map(Number);
  return w > 0 && h > 0 ? w / h : 16 / 9;
}

/** Even pixel size for an aspect, with the short side at the chosen resolution. */
function canvasSize(aspect, resolution) {
  const ratio = aspectRatioValue(aspect);
  const even = value => Math.max(2, Math.round(value / 2) * 2);
  return ratio >= 1 ? [even(resolution * ratio), even(resolution)] : [even(resolution), even(resolution / ratio)];
}

function originalMediaAsset() {
  const bg = project.background || {};
  if (bg.type === "image" && bg.imageAsset?.url) return { kind: "image", url: bg.imageAsset.url };
  if (bg.type === "video" && bg.videoAsset?.url) return { kind: "video", url: bg.videoAsset.url };
  const clip = [...(bg.clips || [])].filter(item => item.asset?.url && ["image", "video"].includes(item.asset.kind))
    .sort((a, b) => a.start - b.start)[0];
  return bg.footageEnabled && clip ? { kind: clip.asset.kind, url: clip.asset.url } : null;
}

function mediaRatio(asset) {
  return new Promise(resolve => {
    const done = (w, h) => resolve(w > 0 && h > 0 ? w / h : null);
    if (asset.kind === "image") {
      const img = new Image();
      img.onload = () => done(img.naturalWidth, img.naturalHeight);
      img.onerror = () => resolve(null);
      img.src = asset.url;
    } else {
      const video = document.createElement("video");
      video.preload = "metadata"; video.muted = true;
      video.onloadedmetadata = () => { done(video.videoWidth, video.videoHeight); video.removeAttribute("src"); video.load(); };
      video.onerror = () => resolve(null);
      video.src = asset.url;
    }
  });
}

/** Re-measure the original media when it changed; cheap enough to call on every save. */
async function refreshOriginalRatio() {
  const asset = originalMediaAsset();
  const key = asset ? asset.url : "";
  if (key === originalSource) return;
  originalSource = key;
  const ratio = asset ? await mediaRatio(asset) : null;
  if (key !== originalSource) return;
  const next = ratio || 16 / 9;
  if (Math.abs(next - originalRatio) < 1e-4) return;
  originalRatio = next;
  if (project.canvas.aspect === "original") setCanvasDimensions();
}

function aspectLabel(aspect) {
  return aspect === "original" ? "Original" : aspect;
}

function refreshRatioButton() {
  const aspect = project.canvas.aspect;
  $("#ratioButton span").textContent = aspectLabel(aspect);
  $$("#ratioMenu button").forEach(button => button.classList.toggle("active", button.dataset.value === aspect));
}

function ratioIcon(value) {
  const ratio = value === "original" ? 0 : aspectRatioValue(value);
  if (!ratio) return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4"/></svg>';
  const w = ratio >= 1 ? 18 : 18 * ratio, h = ratio >= 1 ? 18 / ratio : 18;
  return `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="${(12 - w / 2).toFixed(1)}" y="${(12 - h / 2).toFixed(1)}" width="${w.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5"/></svg>`;
}

function setAspect(value) {
  project.canvas.aspect = value;
  els.aspectSelect.value = value;
  setCanvasDimensions();
  refreshRatioButton();
}

function initRatio() {
  const select = els.aspectSelect;
  select.replaceChildren(...ASPECT_RATIOS.map(item => new Option(`${item.label} · ${item.hint}`, item.value)));
  select.value = project.canvas.aspect;
  select.addEventListener("change", refreshRatioButton);
  const menu = $("#ratioMenu");
  for (const item of ASPECT_RATIOS) {
    const button = document.createElement("button");
    button.type = "button"; button.dataset.value = item.value;
    button.innerHTML = `${ratioIcon(item.value)}<strong></strong><small></small>`;
    $("strong", button).textContent = item.label;
    $("small", button).textContent = item.hint;
    menu.append(button);
  }
  const toggle = $("#ratioButton");
  toggle.addEventListener("click", event => {
    event.stopPropagation();
    menu.hidden = !menu.hidden;
    const box = toggle.getBoundingClientRect();
    menu.style.top = `${box.bottom + 6}px`;
    menu.style.left = `${Math.max(8, box.right - 236)}px`;
    toggle.setAttribute("aria-expanded", String(!menu.hidden));
  });
  menu.addEventListener("click", event => {
    const value = event.target.closest("button")?.dataset.value;
    if (!value) return;
    setAspect(value);
    menu.hidden = true;
  });
  document.addEventListener("pointerdown", event => {
    if (!event.target.closest("#ratioMenu, #ratioButton")) menu.hidden = true;
  });
  document.addEventListener("keydown", event => { if (event.key === "Escape") menu.hidden = true; });
  refreshRatioButton();
  refreshOriginalRatio();
}

initRatio();
