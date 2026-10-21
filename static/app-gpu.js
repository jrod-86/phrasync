"use strict";

// GPU picker: lets transcription run on a chosen NVIDIA card while another is
// busy. The choice belongs to this computer, not the project.

const GPU_KEY = "karaokesesh.gpu";

function chosenGpu() {
  const value = $("#whisperGpu")?.value || "auto";
  return value === "auto" ? null : Number(value);
}

function gpuLabel(gpu) {
  const used = gpu.memoryUsedMb, total = gpu.memoryTotalMb;
  const memory = used != null && total ? ` · ${(used / 1024).toFixed(1)} of ${(total / 1024).toFixed(0)} GB in use` : "";
  return `GPU ${gpu.index}: ${gpu.name}${memory}`;
}

async function loadGpuChoices() {
  const select = $("#whisperGpu");
  if (!select) return;
  let saved = "auto";
  try { saved = localStorage.getItem(GPU_KEY) || "auto"; } catch { /* storage blocked */ }
  try {
    const { gpus, pinned } = await api("/api/gpus");
    select.replaceChildren(new Option(pinned ? "Set by launcher" : "Auto: first GPU", "auto"),
      ...gpus.map(gpu => new Option(gpuLabel(gpu), String(gpu.index))));
    select.disabled = Boolean(pinned) || gpus.length < 2;
  } catch { /* keep the Auto option */ }
  if ([...select.options].some(option => option.value === saved)) select.value = saved;
}

$("#whisperGpu")?.addEventListener("change", event => {
  try { localStorage.setItem(GPU_KEY, event.target.value); } catch { /* storage blocked */ }
});
loadGpuChoices();
