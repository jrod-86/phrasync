"use strict";

// Vocal remover: splits the song into an instrumental and a vocal stem. The
// track picked under the song plays in the preview and goes into the export;
// transcription and timing analysis keep listening to the vocals and the
// original song, whatever plays.

let currentStemsJob = null;
let stemsPollTimer = null;

/** The stems that belong to the song loaded now, or null. */
function validStems() {
  const stems = project.stems;
  return stems?.original?.id && stems.original.id === project.sourceAssetId
    && stems.instrumental?.id && stems.vocals?.id ? stems : null;
}

/** Whisper hears the isolated vocals when they exist: no band to mishear. */
function transcriptionAssetId() {
  return validStems()?.vocals.id || project.sourceAssetId || project.audioAssetId;
}

function refreshStemsControls() {
  const stems = validStems();
  const track = stems ? (project.songTrack || "original") : "original";
  $("#songTrackBox").hidden = !stems;
  $("#removeVocalsButton").hidden = Boolean(stems) || Boolean(currentStemsJob);
  $("#removeVocalsButton").disabled = !project.audioAssetId;
  $$("#songTrack button").forEach(button => button.classList.toggle("active", button.dataset.value === track));
}

function chooseSongTrack(track) {
  const stems = validStems();
  if (!stems) return;
  const asset = stems[track] || stems.original;
  const resume = !els.audioPlayer.paused;
  const at = currentPlaybackTime();
  project.songTrack = stems[track] ? track : "original";
  project.audio = asset;
  project.audioAssetId = asset.id;
  els.audioName.textContent = asset.name;
  applyAudioPreview();
  els.audioPlayer.addEventListener("loadedmetadata", () => {
    seekTo(at);
    if (resume) els.audioPlayer.play().catch(() => {});
  }, { once: true });
  refreshStemsControls(); scheduleSave();
}

function showStemsProgress(job) {
  const percent = Math.max(0, Math.min(100, Math.round(Number(job.progress || 0) * 100)));
  $("#stemsProgress").hidden = false;
  $("#stemsMessage").textContent = job.message || "Removing vocals…";
  $("#stemsPercent").value = `${percent}%`;
  $("#stemsProgressBar").style.width = `${percent}%`;
}

function finishStems() {
  if (stemsPollTimer) clearTimeout(stemsPollTimer);
  stemsPollTimer = null;
  currentStemsJob = null;
  $("#stemsProgress").hidden = true;
  $("#cancelStems").disabled = false;
  refreshStemsControls();
}

async function pollStems() {
  if (!currentStemsJob) return;
  try {
    const job = await api(`/api/stems/${currentStemsJob}`);
    showStemsProgress(job);
    if (job.state === "complete") {
      const original = project.audio?.id === project.sourceAssetId ? project.audio : validStems()?.original || project.audio;
      project.stems = { original, instrumental: job.result.instrumental, vocals: job.result.vocals };
      finishStems();
      chooseSongTrack("instrumental");
      setAssetStatus("Vocals removed. The instrumental now plays and exports; switch back to the full song any time.", "success");
      return toast("Vocals removed.", "success");
    }
    if (job.state === "cancelled" || job.state === "failed") {
      const message = job.state === "failed" ? (job.error || "Vocal removal failed") : "Vocal removal stopped.";
      setAssetStatus(message, job.state === "failed" ? "error" : "");
      toast(message, job.state === "failed" ? "error" : "");
      return finishStems();
    }
    stemsPollTimer = setTimeout(pollStems, 700);
  } catch (error) {
    setAssetStatus(error.message, "error");
    finishStems();
  }
}

async function removeVocals() {
  if (!project.sourceAssetId || currentStemsJob) return;
  try {
    const job = await api("/api/stems", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ assetId: project.sourceAssetId, gpu: chosenGpu() })
    });
    currentStemsJob = job.id;
    refreshStemsControls();
    showStemsProgress(job);
    pollStems();
  } catch (error) {
    setAssetStatus(error.message, "error");
    toast(error.message, "error");
  }
}

$("#removeVocalsButton").addEventListener("click", removeVocals);
$("#cancelStems").addEventListener("click", async () => {
  if (!currentStemsJob) return;
  $("#cancelStems").disabled = true;
  try { await api(`/api/stems/${currentStemsJob}/cancel`, { method: "POST" }); }
  catch (error) { $("#cancelStems").disabled = false; toast(error.message, "error"); }
});
$$("#songTrack button").forEach(button => button.addEventListener("click", () => chooseSongTrack(button.dataset.value)));
