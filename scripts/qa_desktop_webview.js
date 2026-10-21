"use strict";

const endpoint = process.argv[2] || "http://127.0.0.1:9223";

async function rpc(webSocketUrl, method, params = {}) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(webSocketUrl);
    const timer = setTimeout(() => reject(new Error(`${method} timed out`)), 10000);
    socket.addEventListener("open", () => socket.send(JSON.stringify({ id: 1, method, params })));
    socket.addEventListener("message", event => {
      const message = JSON.parse(event.data);
      if (message.id !== 1) return;
      clearTimeout(timer);
      socket.close();
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    });
    socket.addEventListener("error", () => reject(new Error(`Cannot connect for ${method}`)));
  });
}

async function main() {
  const [version, pages] = await Promise.all([
    fetch(`${endpoint}/json/version`).then(response => response.json()),
    fetch(`${endpoint}/json`).then(response => response.json()),
  ]);
  const page = pages.find(item => item.type === "page");
  if (!page) throw new Error("KaraokeSesh WebView page not found");
  const system = await rpc(version.webSocketDebuggerUrl, "SystemInfo.getInfo");
  const expression = `new Promise(resolve => {
    const frames = [];
    const longTasks = [];
    let previewPaints = 0;
    let previousPaint = lastInteractiveFrame;
    let observer;
    try {
      observer = new PerformanceObserver(list => longTasks.push(...list.getEntries().map(e => e.duration)));
      observer.observe({type: 'longtask'});
    } catch {}
    const started = performance.now();
    function frame(now) {
      frames.push(now);
      if (lastInteractiveFrame !== previousPaint) {
        previewPaints += 1;
        previousPaint = lastInteractiveFrame;
      }
      if (now - started < 2000) return requestAnimationFrame(frame);
      observer?.disconnect();
      const canvas = document.querySelector('#visualCanvas');
      const rect = canvas.getBoundingClientRect();
      const probe = document.createElement('canvas');
      const gl = probe.getContext('webgl2') || probe.getContext('webgl');
      const debug = gl?.getExtension('WEBGL_debug_renderer_info');
      resolve({
        title: document.title,
        url: location.href,
        desktopHost: document.documentElement.classList.contains('desktop-host'),
        animationFps: Math.round((frames.length - 1) * 10000 / (frames.at(-1) - frames[0])) / 10,
        previewPaintFps: Math.round(previewPaints * 5) / 10,
        longTaskCount: longTasks.length,
        longestTaskMs: Math.round(Math.max(0, ...longTasks)),
        canvasScale: Math.round(canvas.width / Math.max(1, rect.width) * 100) / 100,
        webglRenderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : gl?.getParameter(gl.RENDERER),
      });
    }
    requestAnimationFrame(frame);
  })`;
  const evaluated = await rpc(page.webSocketDebuggerUrl, "Runtime.evaluate", {
    expression, awaitPromise: true, returnByValue: true,
  });
  const devices = system.gpu?.devices || [];
  console.log(JSON.stringify({
    page: evaluated.result.value,
    gpuDevices: devices.map(device => ({vendor: device.vendorString, device: device.deviceString})),
    featureStatus: system.gpu?.featureStatus,
  }, null, 2));
}

main().catch(error => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
