import shutil
import subprocess
from pathlib import Path

import pytest


def test_long_cue_lists_mount_bounded_cards_and_preserve_edit_targets():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    source = (Path(__file__).resolve().parent.parent / "static/app-cues.js").read_text(encoding="utf-8")
    harness = r"""
const assert = require('node:assert/strict');
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.dataset = {}; this.style = {}; this.events = {}; this.classList = {toggle(){}}; }
  append(...nodes) { for (const n of nodes) this.children.push(...(n.tag === 'fragment' ? n.children : [n])); }
  set textContent(value) { this.text = value; this.children = []; }
  get textContent() { return this.text; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, handler) { this.events[name] = handler; }
  querySelectorAll(selector) { return this.children.flatMap(n => [(n.className || '').split(' ').includes(selector.slice(1)) ? n : null, ...n.querySelectorAll(selector)]).filter(Boolean); }
  scrollIntoView() { this.scrolled = true; }
}
const document = {documentElement: {lang: 'en'}, events: {}, createElement: tag => new Element(tag),
  createDocumentFragment: () => new Element('fragment'), addEventListener(name, fn) { this.events[name] = fn; }};
let project = {cues: Array.from({length: 5000}, (_, i) => ({id: `cue-${i}`, start: i * 3, end: i * 3 + 2, text: `Line ${i}`})), timing: {}};
let selectedCueId = 'cue-0', currentCueId = null, selectedWordIndex = 0, tapQueue = [], timeline = null;
const els = {cueList: new Element('div'), cueCount: new Element('span')};
const normalizeCues = () => {}, updateWordLabel = () => {}, updateDurationUI = () => {}, scheduleSave = () => {}, seekTo = () => {}, toast = () => {};
const $$ = (selector, root) => root.querySelectorAll(selector);
"""
    checks = r"""
const cards = () => els.cueList.querySelectorAll('.cue-card');
const nav = () => els.cueList.children[0];
renderCueList();
els.cueList.scrollTop = 240;
renderCueList({preservePage: true});
assert.equal(els.cueList.scrollTop, 240);
assert.equal(cards().length, 100);
assert.equal(nav().children[0].disabled, true);
nav().children[2].events.click();
assert.equal(cards()[0].dataset.id, 'cue-100');
assert.equal(cards()[0].children[0].textContent, '101');
els.cueList.scrollTop = 320; selectedCueId = 'cue-4999';
renderCueList({preservePage: true});
assert.equal(cards()[0].dataset.id, 'cue-100');
assert.equal(els.cueList.scrollTop, 320);
selectedCueId = 'cue-0'; renderCueList({preservePage: true});
assert.equal(selectedCueId, 'cue-0'); // browsing never silently changes edit selection
const text = cards()[0].children[1].children[1];
text.value = 'Edited on page two'; text.events.input();
assert.equal(project.cues[100].text, 'Edited on page two');
assert.equal(project.cues[0].text, 'Line 0');
cards()[1].children[2].events.click();
assert.ok(!project.cues.some(c => c.id === 'cue-101'));
assert.equal(cards().length, 100);
selectedCueId = 'cue-4999'; revealCueInList(selectedCueId);
assert.ok(cards().some(c => c.dataset.id === selectedCueId && c.scrolled));
assert.equal(nav().children[2].disabled, true);
const jump = nav().children[3]; jump.value = '205'; jump.events.change();
assert.equal(selectedCueId, project.cues[204].id);
assert.ok(cards().some(c => c.dataset.id === selectedCueId));
document.documentElement.lang = 'it'; document.events['phrasync-language-change']();
assert.equal(nav().children[0].textContent, 'Precedente');
project.cues = project.cues.slice(0, 3); selectedCueId = project.cues[0].id; renderCueList();
assert.equal(cards().length, 3);
assert.equal(els.cueList.children.length, 3); // unchanged short-project layout
project.cues = []; renderCueList();
assert.equal(cards().length, 0);
"""
    result = subprocess.run([node, "-"], input=harness + source + checks, capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
