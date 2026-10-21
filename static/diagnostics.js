"use strict";

// The app was called Phrasync before KaraokeSesh. This is the first script to
// load, so copy saved settings and the autosave across before anything reads them.
(() => {
  try {
    for (const key of Object.keys(localStorage)) {
      if (!key.startsWith("phrasync.")) continue;
      const renamed = `karaokesesh.${key.slice("phrasync.".length)}`;
      if (localStorage.getItem(renamed) === null) localStorage.setItem(renamed, localStorage.getItem(key));
    }
  } catch {}
})();

// Deliberately independent from app.js: support remains accessible even when
// the editor fails before its usual event handlers are installed.
(() => {
  const pending = [];
  const recent = [];
  const endpoint = "/api/diagnostics/events";
  let reportText = "";
  let flushing = false;
  const translate = text => window.t?.(text) || text;

  function record(level, category, message) {
    const entry = {
      level: level === "error" ? "error" : level === "warning" ? "warning" : "info",
      category: String(category || "frontend").slice(0, 40),
      message: String(message || "").slice(0, 1800)
    };
    if (!entry.message) return;
    recent.push(`${new Date().toISOString()} | ${entry.level} | ${entry.category} | ${entry.message}`);
    if (recent.length > 100) recent.shift();
    pending.push(entry);
    flush();
  }

  async function flush() {
    if (flushing || !pending.length) return;
    flushing = true;
    try {
      while (pending.length) {
        const response = await fetch(endpoint, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(pending[0]), keepalive: true
        });
        if (!response.ok) break;
        pending.shift();
      }
    } catch {
      // A failed local server must not stop the editor or recursively log.
    } finally {
      flushing = false;
    }
  }

  window.addEventListener("error", event => {
    const source = event.filename ? new URL(event.filename, location.href).pathname : event.target?.src ? "resource" : "unknown script";
    record("error", "javascript", `${event.message || "Resource load failed"} at ${source}:${event.lineno || 0}:${event.colno || 0}\n${event.error?.stack || ""}`);
  }, true);
  window.addEventListener("unhandledrejection", event => {
    record("error", "javascript-promise", event.reason?.stack || event.reason || "Unhandled promise rejection");
  });
  window.KaraokeSeshDiagnostics = { record, recent };

  async function refresh() {
    const output = document.querySelector("#diagnosticsOutput");
    const status = document.querySelector("#diagnosticsStatus");
    if (!output || !status) return;
    status.textContent = translate("Loading local report…");
    try {
      const response = await fetch("/api/diagnostics", { cache: "no-store" });
      if (!response.ok) throw new Error(`Local diagnostics returned ${response.status}`);
      reportText = await response.text();
      output.textContent = reportText;
      status.textContent = translate("Report ready — review before sharing.");
    } catch (error) {
      reportText = `Local report unavailable: ${error.message}\n\nCurrent window events\n${recent.join("\n")}`;
      output.textContent = reportText;
      status.textContent = translate("The local report could not be loaded.");
    }
  }

  function init() {
    const button = document.querySelector("#diagnosticsButton");
    const dialog = document.querySelector("#diagnosticsDialog");
    if (!button || !dialog) return;
    button.addEventListener("click", () => {
      if (!dialog.open) dialog.showModal();
      refresh();
    });
    document.querySelector("#diagnosticsClose").addEventListener("click", () => dialog.close());
    const tracedControls = new Set(["audioPick", "playButton", "renderButton", "confirmRender", "transcribeButton", "autoAlignButton"]);
    document.addEventListener("click", event => {
      const control = event.target.closest?.("button");
      if (control && tracedControls.has(control.id)) record("info", "action", control.id);
    }, true);
    document.querySelector("#diagnosticsRefresh").addEventListener("click", refresh);
    document.querySelector("#diagnosticsCopy").addEventListener("click", async () => {
      if (!reportText) await refresh();
      try {
        await navigator.clipboard.writeText(reportText);
        document.querySelector("#diagnosticsStatus").textContent = translate("Report copied. Review before sharing.");
      } catch {
        document.querySelector("#diagnosticsStatus").textContent = translate("Copy unavailable. Download the report instead.");
      }
    });
    document.querySelector("#diagnosticsDownload").addEventListener("click", async () => {
      if (!reportText) await refresh();
      const blob = new Blob([reportText], { type: "text/plain;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `KaraokeSesh-support-${new Date().toISOString().slice(0, 10)}.txt`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
    record("info", "frontend", `Document loaded: ${location.pathname}, version URL ${new URLSearchParams(location.search).get("app_version") || "none"}`);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init, { once: true });
  else init();
  window.addEventListener("online", flush);
  setTimeout(flush, 2000);
})();
