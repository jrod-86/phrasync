"use strict";

// Karaoke Credit Crawl countdown: after a long silence, 3-2-1 dots appear to
// the left of the line the singer comes back in on. The leftmost dot goes
// first, so the last one left sits right beside the opening word.
let crawlCountdownMark = null;

function crawlCountdownElement() {
  if (!crawlCountdownMark) {
    crawlCountdownMark = document.createElement("i");
    crawlCountdownMark.className = "crawl-countdown";
    crawlCountdownMark.setAttribute("aria-hidden", "true");
    crawlCountdownMark.append(...[3, 2, 1].map(() => document.createElement("b")));
  }
  return crawlCountdownMark;
}

function updateCrawlCountdown(time, crawlMode, spec) {
  const found = crawlMode ? K().crawlCountdown(project.cues, time, spec) : null;
  const word = found && lyricCues.get(found.cue.id)?.nodes[0]?.el;
  if (!word) {
    crawlCountdownMark?.remove();
    return;
  }
  const mark = crawlCountdownElement();
  if (mark.parentNode !== word) word.prepend(mark);
  if (mark.dataset.count !== String(found.count)) mark.dataset.count = String(found.count);
}
