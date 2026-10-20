"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const clone = value => JSON.parse(JSON.stringify(value));
const STORAGE_KEY = "phrasync.project.v1";
const THEME_KEY = "phrasync.theme";
// The app shipped as VerseFrame before Phrasync; read those keys once so an
// existing autosave and theme choice survive the rename.
const LEGACY_STORAGE_KEY = "verseframe.project.v1";
const LEGACY_THEME_KEY = "verseframe.theme";
const IS_DESKTOP_HOST = new URLSearchParams(location.search).get("desktop") === "1";
document.documentElement.classList.toggle("desktop-host", IS_DESKTOP_HOST);

const DEFAULT_PROJECT = {
  version: 2,
  mode: "lyric",
  title: "Untitled lyric video",
  canvas: { aspect: "original", width: 1920, height: 1080, fps: 30 },
  duration: 8,
  audioAssetId: null,
  audio: null,
  sourceAssetId: null,
  sourceKind: "audio",
  background: {
    type: "dynamic",
    footageEnabled: false,
    clips: [],
    mediaLibrary: [],
    effects: { bw: 0, pendulum: 0, shake: 0, flash: 0, gradient: 0, particles: 0, spectrum: 0, bpm: 0, color1: "#6b21a8", color2: "#ec4899" },
    visual: "aurora",
    sceneKit: "japan",
    sceneDirection: "forward",
    artStyle: "cinematic",
    secondaryMotion: "none",
    motionAmount: .35,
    textSpace: "flat",
    sceneBeat: false,
    sceneWave: false,
    waveColor: "#4de2ff",
    waveIntensity: 1,
    sceneSpeed: 1,
    sceneDensity: 1,
    sceneSeed: 1337,
    environmentMode: "manual",
    weather: "clear",
    daytime: "sunset",
    season: "summer",
    assetId: null,
    url: null,
    name: null,
    imageAsset: null,
    videoAsset: null,
    shade: 0.28,
    visualIntensity: 0.90,
    grain: 0.14,
    motion: 0,
    blur: 0,
    brightness: 1,
    backgroundColor: "#080812",
    secondaryColor: "#5cd7ff"
  },
  timing: {
    offset: 0,
    snapWindow: 0.14,
    snapStrength: 0.85,
    snapPhrases: false,
    snapMode: "onset",
    bpm: 0,
    beatOffset: 0
  },
  style: {
    preset: "kinetic-slam",
    fontPreset: "impact",
    fontAssetId: null,
    fontName: null,
    fontSize: 160,
    topScale: 0.58,
    maxWidth: 88,
    positionY: 52,
    offset3DX: 0,
    offset3DY: 0,
    lineGap: -8,
    textColor: "#ffffff",
    accentColor: "#ff3d7f",
    accentColor2: "#8f5bff",
    strokeColor: "#05040c",
    strokeWidth: 3,
    shadow: 7,
    uppercase: true,
    animation: 1,
    wordLead: 0.06,
    beatReact: true
  },
  export: { crf: 18, preset: "medium", bitrateMbps: null },
  cues: [
    { id: "cue-1", start: 0, end: 2.6, text: "MAKE EVERY\nFRAME MOVE", words: [] },
    { id: "cue-2", start: 2.6, end: 5.2, text: "TYPE TO\nTHE BEAT", words: [] },
    { id: "cue-3", start: 5.2, end: 8, text: "CREATE. SYNC.\nEXPORT.", words: [] }
  ]
};
function deepMerge(base, incoming) {
  if (Array.isArray(base)) return Array.isArray(incoming) ? incoming : clone(base);
  if (base && typeof base === "object") {
    const result = { ...base };
    if (incoming && typeof incoming === "object") {
      for (const [key, value] of Object.entries(incoming)) {
        result[key] = key in base ? deepMerge(base[key], value) : value;
      }
    }
    return result;
  }
  return incoming ?? base;
}

const LEGACY_MOTION = { pop: 1, rise: 1, slide: 1, fade: 0.6, none: 0 };
const LEGACY_STYLE_PRESETS = { "center-punch": "kinetic-slam", karaoke: "wipe-fill", neon: "neon-flux" };

/** Bring pre-kinetic saved projects onto the current schema. */
function migrateProject(input) {
  const next = deepMerge(DEFAULT_PROJECT, input);
  next.version = 2;
  if (!["karaoke", "lyric"].includes(next.mode)) next.mode = "lyric";
  if (!next.sourceAssetId && next.audioAssetId) next.sourceAssetId = next.audioAssetId;
  if (!next.sourceKind) next.sourceKind = next.audio?.kind || "audio";
  const legacyDemo = ["STAND YOUR\nGROUND", "MAKE EVERY WORD\nHIT HARDER", "BUILD IT.\nPLAY IT."];
  if (legacyDemo.every((text, index) => next.cues[index]?.text === text)) {
    if (next.title === "Stand Your Ground") next.title = DEFAULT_PROJECT.title;
    next.cues = clone(DEFAULT_PROJECT.cues);
  }
  if (LEGACY_STYLE_PRESETS[next.style.preset]) next.style.preset = LEGACY_STYLE_PRESETS[next.style.preset];
  if (next.style.preset === "credit-crawl") next.mode = "karaoke"; // crawl projects made before the Karaoke mode
  if (typeof next.style.animation === "string") {
    const parsed = Number(next.style.animation);
    next.style.animation = Number.isFinite(parsed) ? parsed : (LEGACY_MOTION[next.style.animation] ?? 1);
  }
  if (typeof next.style.beatReact !== "boolean") next.style.beatReact = true;
  return next;
}

function loadLocalProject() {
  try {
    let raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      raw = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (raw) localStorage.setItem(STORAGE_KEY, raw);
    }
    return raw ? migrateProject(JSON.parse(raw)) : clone(DEFAULT_PROJECT);
  } catch {
    return clone(DEFAULT_PROJECT);
  }
}

let project = loadLocalProject();
let health = null;
let selectedCueId = project.cues[0]?.id || null;
let currentCueId = null;
let virtualTime = 0;
let virtualPlaying = false;
let virtualStartedAt = 0;
let virtualStartedTime = 0;
let saveTimer = null;
let currentRenderJob = null;
let renderPollTimer = null;
let currentTranscriptionJob = null;
let transcriptionPollTimer = null;
let audioContext = null;
let analyser = null;
let audioSource = null;
let frequencyData = null;
let particles = [];
let lastParticleSize = "";
let analysis = null;
let analysisPending = false;
let timeline = null;
const lyricCues = new Map();
let selectedWordIndex = 0;
let tapArmed = false;
let tapQueue = [];

const els = {
  root: document.documentElement,
  projectTitle: $("#projectTitle"),
  projectMode: $("#projectMode"),
  modeDescription: $("#modeDescription"),
  engineStatus: $("#engineStatus"),
  settingsButton: $("#settingsButton"),
  shutdownButton: $("#shutdownButton"),
  themeToggle: $("#themeToggle"),
  criticButton: $("#criticButton"),
  renderButton: $("#renderButton"),
  audioInput: $("#audioInput"),
  audioPick: $("#audioPick"),
  audioName: $("#audioName"),
  audioHint: $("#audioHint"),
  backgroundType: $("#backgroundType"),
  dynamicControls: $("#dynamicControls"),
  backgroundUploadWrap: $("#backgroundUploadWrap"),
  backgroundInput: $("#backgroundInput"),
  backgroundPick: $("#backgroundPick"),
  backgroundName: $("#backgroundName"),
  backgroundHint: $("#backgroundHint"),
  visualSelect: $("#visualSelect"),
  sceneControls: $("#sceneControls"),
  sceneKit: $("#sceneKit"),
  sceneDirection: $("#sceneDirection"),
  sceneArtStyle: $("#sceneArtStyle"),
  secondaryMotion: $("#secondaryMotion"),
  motionAmount: $("#motionAmount"),
  textSpace: $("#textSpace"),
  sceneBeat: $("#sceneBeat"),
  sceneWave: $("#sceneWave"),
  waveControls: $("#waveControls"),
  waveColor: $("#waveColor"),
  waveIntensity: $("#waveIntensity"),
  sceneSpeed: $("#sceneSpeed"),
  sceneDensity: $("#sceneDensity"),
  sceneReseed: $("#sceneReseed"),
  environmentControls: $("#environmentControls"),
  environmentMode: $("#environmentMode"),
  manualEnvironmentControls: $("#manualEnvironmentControls"),
  weather: $("#weather"),
  daytime: $("#daytime"),
  season: $("#season"),
  environmentResolved: $("#environmentResolved"),
  ocrInput: $("#ocrInput"),
  ocrPick: $("#ocrPick"),
  lyricsInput: $("#lyricsInput"),
  lyricsPick: $("#lyricsPick"),
  lyricsPickTitle: $("#lyricsPickTitle"),
  assetStatus: $("#assetStatus"),
  whisperModel: $("#whisperModel"),
  whisperLanguage: $("#whisperLanguage"),
  vadFilter: $("#vadFilter"),
  transcribeButton: $("#transcribeButton"),
  transcriptionSectionName: $("#transcriptionSectionName"),
  transcriptionNote: $("#transcriptionNote"),
  transcriptionProgress: $("#transcriptionProgress"),
  transcriptionMessage: $("#transcriptionMessage"),
  transcriptionPercent: $("#transcriptionPercent"),
  transcriptionProgressBar: $("#transcriptionProgressBar"),
  transcriptionTrack: $("#transcriptionProgress .transcription-track"),
  cancelTranscription: $("#cancelTranscription"),
  stylePreset: $("#stylePreset"),
  fontPreset: $("#fontPreset"),
  fontInput: $("#fontInput"),
  fontPick: $("#fontPick"),
  fontSize: $("#fontSize"),
  topScale: $("#topScale"),
  maxWidth: $("#maxWidth"),
  positionY: $("#positionY"),
  text3dOffsetControls: $("#text3dOffsetControls"),
  offset3DX: $("#offset3DX"),
  offset3DY: $("#offset3DY"),
  lineGap: $("#lineGap"),
  textColor: $("#textColor"),
  accentColor: $("#accentColor"),
  accentColor2: $("#accentColor2"),
  strokeColor: $("#strokeColor"),
  animationSelect: $("#animationSelect"),
  uppercaseToggle: $("#uppercaseToggle"),
  strokeWidth: $("#strokeWidth"),
  shadow: $("#shadow"),
  shade: $("#shade"),
  visualIntensity: $("#visualIntensity"),
  grain: $("#grain"),
  motion: $("#motion"),
  blur: $("#blur"),
  backgroundColor: $("#backgroundColor"),
  secondaryColor: $("#secondaryColor"),
  aspectSelect: $("#aspectSelect"),
  resolutionSelect: $("#resolutionSelect"),
  fpsSelect: $("#fpsSelect"),
  qualitySelect: $("#qualitySelect"),
  bitrateInput: $("#bitrateInput"),
  bitrateField: $("#bitrateField"),
  renderDirectoryInput: $("#renderDirectoryInput"),
  safeAreaToggle: $("#safeAreaToggle"),
  stageShell: $("#stageShell"),
  stage: $("#stage"),
  visualCanvas: $("#visualCanvas"),
  glCanvas: $("#glCanvas"),
  backgroundImage: $("#backgroundImage"),
  backgroundVideo: $("#backgroundVideo"),
  stageShade: $("#stageShade"),
  stageTexture: $("#stageTexture"),
  safeArea: $("#safeArea"),
  lyricDisplay: $("#lyricDisplay"),
  noAudioHint: $("#noAudioHint"),
  previewResolution: $("#previewResolution"),
  restartAnimation: $("#restartAnimation"),
  fullscreenButton: $("#fullscreenButton"),
  playButton: $("#playButton"),
  currentTime: $("#currentTime"),
  durationTime: $("#durationTime"),
  seekBar: $("#seekBar"),
  muteButton: $("#muteButton"),
  volumeSlider: $("#volumeSlider"),
  audioPlayer: $("#audioPlayer"),
  currentCueLabel: $("#currentCueLabel"),
  autosaveStatus: $("#autosaveStatus"),
  bulkLyrics: $("#bulkLyrics"),
  appendBulkButton: $("#appendBulkButton"),
  replaceBulkButton: $("#replaceBulkButton"),
  cueCount: $("#cueCount"),
  cuePanelTitle: $("#cuePanelTitle"),
  bulkLyricsLabel: $("#bulkLyricsLabel"),
  cueList: $("#cueList"),
  addCueButton: $("#addCueButton"),
  sortCuesButton: $("#sortCuesButton"),
  nudgeBackButton: $("#nudgeBackButton"),
  nudgeForwardButton: $("#nudgeForwardButton"),
  exportSrtButton: $("#exportSrtButton"),
  exportFormat: $("#exportFormat"),
  projectInput: $("#projectInput"),
  loadProjectButton: $("#loadProjectButton"),
  saveProjectButton: $("#saveProjectButton"),
  resetProjectButton: $("#resetProjectButton"),
  reportDialog: $("#reportDialog"),
  reportTitle: $("#reportTitle"),
  scoreRing: $("#scoreRing"),
  scoreValue: $("#scoreValue"),
  reportSummary: $("#reportSummary"),
  reportList: $("#reportList"),
  checksList: $("#checksList"),
  settingsDialog: $("#settingsDialog"),
  hfTokenStatus: $("#hfTokenStatus"),
  hfTokenInput: $("#hfTokenInput"),
  hfTokenReveal: $("#hfTokenReveal"),
  hfTokenRemove: $("#hfTokenRemove"),
  hfTokenSave: $("#hfTokenSave"),
  renderDialog: $("#renderDialog"),
  renderTitle: $("#renderTitle"),
  renderClose: $("#renderClose"),
  renderPercent: $("#renderPercent"),
  renderProgress: $("#renderProgress"),
  renderMessage: $("#renderMessage"),
  renderResult: $("#renderResult"),
  renderMeta: $("#renderMeta"),
  downloadRender: $("#downloadRender"),
  renderDirectory: $("#renderDirectory"),
  chooseRenderDirectory: $("#chooseRenderDirectory"),
  openRenderDirectory: $("#openRenderDirectory"),
  openDefaultRenderDirectory: $("#openDefaultRenderDirectory"),
  confirmRender: $("#confirmRender"),
  renderError: $("#renderError"),
  cancelRender: $("#cancelRender"),
  toastStack: $("#toastStack"),
  presetHint: $("#presetHint"),
  beatReactToggle: $("#beatReactToggle"),
  syncSummary: $("#syncSummary"),
  analyzeButton: $("#analyzeButton"),
  autoAlignButton: $("#autoAlignButton"),
  timingOffset: $("#timingOffset"),
  wordLead: $("#wordLead"),
  snapWindow: $("#snapWindow"),
  snapStrength: $("#snapStrength"),
  snapPhrasesToggle: $("#snapPhrasesToggle"),
  alignNote: $("#alignNote"),
  timelineDock: $("#timelineDock"),
  dockGrip: $("#dockGrip"),
  timelineMeta: $("#timelineMeta"),
  timelineWrap: $("#timelineWrap"),
  timelineCanvas: $("#timelineCanvas"),
  snapMode: $("#snapMode"),
  zoomInButton: $("#zoomInButton"),
  zoomOutButton: $("#zoomOutButton"),
  zoomFitButton: $("#zoomFitButton"),
  followToggle: $("#followToggle"),
  selectedWordLabel: $("#selectedWordLabel"),
  wordBack: $("#wordBack"),
  wordForward: $("#wordForward"),
  tapSyncButton: $("#tapSyncButton"),
  splitCueButton: $("#splitCueButton"),
  clearWordsButton: $("#clearWordsButton")
};
const rangeOutputs = {
  fontSize: ["fontSizeOut", value => `${value}`],
  topScale: ["topScaleOut", value => `${value}%`],
  maxWidth: ["maxWidthOut", value => `${value}%`],
  positionY: ["positionYOut", value => `${value}%`],
  offset3DX: ["offset3DXOut", value => `${value > 0 ? "+" : ""}${value.toFixed(2)}`],
  offset3DY: ["offset3DYOut", value => `${value > 0 ? "+" : ""}${value.toFixed(2)}`],
  lineGap: ["lineGapOut", value => `${value}`],
  strokeWidth: ["strokeWidthOut", value => `${value}`],
  shadow: ["shadowOut", value => `${value}`],
  shade: ["shadeOut", value => `${value}%`],
  visualIntensity: ["visualIntensityOut", value => `${value}%`],
  grain: ["grainOut", value => `${value}%`],
  motion: ["motionOut", value => `${value}%`],
  blur: ["blurOut", value => `${value}`],
  timingOffset: ["timingOffsetOut", value => `${value > 0 ? "+" : ""}${value} ms`],
  wordLead: ["wordLeadOut", value => `${value} ms`],
  sceneSpeed: ["sceneSpeedOut", value => `${value}%`],
  motionAmount: ["motionAmountOut", value => `${value}%`],
  sceneDensity: ["sceneDensityOut", value => `${value}%`],
  waveIntensity: ["waveIntensityOut", value => `${value}%`]
};
