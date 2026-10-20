"use strict";

// CapCut-style Studio panel: icon tabs along the top, a narrow rail of
// categories down the side, and one category's controls at a time. The
// controls themselves are the existing ones, moved (never cloned) into their
// category, so every id and listener keeps working.

const SIDEBAR_KEY = "phrasync.sidebar";

const SIDEBAR_ICONS = {
  audio: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
  lyrics: '<path d="M4 6h16M4 11h16M4 16h10"/><path d="M18 15v5l3-2"/>',
  text: '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
  background: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m3 16 5-5 4 4 3-3 6 6"/><circle cx="15.5" cy="8.5" r="1.5"/>',
  canvas: '<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M7 3v3M17 18v3"/>'
};

function sidebarSectionBody(name) {
  return $(`summary[data-section="${name}"]`)?.parentElement.querySelector(":scope > .section-body");
}

/** Children of parent from the first node up to (not including) the stop node. */
function sidebarRun(first, stop) {
  const nodes = [];
  for (let node = first; node && node !== stop; node = node.nextElementSibling) nodes.push(node);
  return nodes;
}

function sidebarLayout() {
  const assets = sidebarSectionBody("assets");
  const type = sidebarSectionBody("type");
  const backgroundLabel = [...assets.querySelectorAll(":scope > .field-label")].find(label => label.nextElementSibling?.id === "backgroundType");
  const footage = $("#footageSection");
  const colour = [$("#colorTheme").closest("label"), $(".color-row", type), $("#strokeWidth").closest("label"), $("#shadow").closest("label")];
  const motion = [$("#animationSelect").closest(".two-columns"), $("#beatReactToggle").closest("label"), $("#crawlControls")];
  const style = [...type.children].filter(node => !colour.includes(node) && !motion.includes(node));
  return [
    { id: "audio", label: "Audio", groups: [
      { id: "song", label: "Song", nodes: [$("#audioInput"), $("#audioPick")] },
      { id: "vocals", label: "Vocal remover", nodes: [$("#removeVocalsButton"), $("#stemsProgress"), $("#songTrackBox")] }
    ] },
    { id: "lyrics", label: "Lyrics", groups: [
      { id: "transcribe", label: "Transcribe", nodes: [...sidebarSectionBody("transcribe").children] },
      { id: "import", label: "Import", nodes: [$(".asset-grid", assets)] },
      { id: "sync", label: "Sync", nodes: [...sidebarSectionBody("sync").children] }
    ] },
    { id: "text", label: "Text", groups: [
      { id: "style", label: "Style", nodes: style },
      { id: "colour", label: "Colour", nodes: colour },
      { id: "motion", label: "Motion", nodes: motion }
    ] },
    { id: "background", label: "Background", groups: [
      { id: "visual", label: "Visual", nodes: sidebarRun(backgroundLabel, footage) },
      { id: "adjust", label: "Adjust", nodes: [...sidebarSectionBody("visual").children] },
      { id: "footage", label: "Footage", nodes: [footage] }
    ] },
    { id: "canvas", label: "Canvas", groups: [
      { id: "format", label: "Format", nodes: [...sidebarSectionBody("export").children] }
    ] }
  ];
}

let sidebarState = { tab: "audio", groups: {} };

function showSidebar(tabId, groupId) {
  const tab = $(`.studio-tab[data-tab="${tabId}"]`);
  if (!tab) return;
  groupId ||= sidebarState.groups[tabId] || $(`.studio-page[data-tab="${tabId}"] .studio-rail button`)?.dataset.group;
  sidebarState.tab = tabId;
  sidebarState.groups[tabId] = groupId;
  $$(".studio-tab").forEach(button => {
    const on = button.dataset.tab === tabId;
    button.classList.toggle("active", on);
    button.setAttribute("aria-selected", String(on));
  });
  $$(".studio-page").forEach(page => { page.hidden = page.dataset.tab !== tabId; });
  const page = $(`.studio-page[data-tab="${tabId}"]`);
  $$(".studio-rail button", page).forEach(button => button.classList.toggle("active", button.dataset.group === groupId));
  $$(".studio-group", page).forEach(group => { group.hidden = group.dataset.group !== groupId; });
  $(".studio-content", page).scrollTop = 0;
  try { localStorage.setItem(SIDEBAR_KEY, JSON.stringify(sidebarState)); } catch { /* storage blocked */ }
}

function buildStudioTabs() {
  const panel = $(".controls-panel");
  const layout = sidebarLayout();
  const tabs = document.createElement("nav");
  tabs.className = "studio-tabs";
  tabs.setAttribute("role", "tablist");
  const pages = document.createElement("div");
  pages.className = "studio-pages";

  for (const tab of layout) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "studio-tab";
    button.dataset.tab = tab.id;
    button.setAttribute("role", "tab");
    button.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${SIDEBAR_ICONS[tab.id]}</svg><span>${t(tab.label)}</span>`;
    button.addEventListener("click", () => showSidebar(tab.id));
    tabs.append(button);

    const page = document.createElement("section");
    page.className = "studio-page";
    page.dataset.tab = tab.id;
    page.setAttribute("role", "tabpanel");
    const rail = document.createElement("div");
    rail.className = "studio-rail";
    const content = document.createElement("div");
    content.className = "studio-content compact-fields";
    for (const group of tab.groups) {
      const item = document.createElement("button");
      item.type = "button";
      item.dataset.group = group.id;
      item.textContent = t(group.label);
      item.addEventListener("click", () => showSidebar(tab.id, group.id));
      rail.append(item);
      const box = document.createElement("div");
      box.className = "studio-group";
      box.dataset.group = group.id;
      box.append(...group.nodes.filter(Boolean));
      content.append(box);
    }
    page.classList.toggle("single", tab.groups.length < 2);
    page.append(rail, content);
    pages.append(page);
  }

  // The old collapsible sections are now empty shells; keep them (some code
  // still updates their titles) but out of sight.
  $$("summary[data-section]", panel).forEach(summary => { summary.parentElement.hidden = true; });
  $(".mode-card", panel).after(tabs, pages);
  // Upload, transcription and import messages show whichever tab is open.
  pages.after($("#assetStatus"));

  // Footage always shows open inside its own category; code that "opens" it
  // (double-clicking the footage lane, Edit clip) brings that category up.
  const footage = $("#footageSection");
  footage.setAttribute("open", "");
  footage.classList.add("studio-footage");
  Object.defineProperty(footage, "open", {
    get: () => true,
    set: value => { if (value) showSidebar("background", "footage"); }
  });

  try { sidebarState = { ...sidebarState, ...JSON.parse(localStorage.getItem(SIDEBAR_KEY) || "{}") }; } catch { /* storage blocked */ }
  showSidebar(layout.some(tab => tab.id === sidebarState.tab) ? sidebarState.tab : "audio");
}

buildStudioTabs();
