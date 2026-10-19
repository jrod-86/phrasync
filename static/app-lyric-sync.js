"use strict";

// Sync to my lyrics: pasted lyrics decide every word and line break, and
// Whisper only lends its timing, so each word gets a real highlight time.

function pastedSyncLyrics() {
  return $("#syncLyrics")?.value.trim() || "";
}

function transcribeButtonLabel() {
  if (pastedSyncLyrics()) return t("Sync my lyrics to the song");
  return t(MODE_COPY[project.mode]?.transcribe || "Transcribe locally");
}

function lyricSyncStatus(result) {
  const report = result.lyricSync;
  const unheard = report.unheardLines?.length || 0;
  const check = unheard ? ` · check ${unheard} line${unheard === 1 ? "" : "s"} Whisper did not hear` : "";
  return `Synced ${report.lines} lyric lines · ${report.heard} of ${report.words} words heard${check}.`;
}

$("#syncLyrics")?.addEventListener("input", event => {
  project.syncLyrics = event.target.value;
  scheduleSave();
  if (!currentTranscriptionJob) els.transcribeButton.textContent = transcribeButtonLabel();
});
