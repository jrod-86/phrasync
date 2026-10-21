"""Exercise update controls, long cue lists and export in an isolated browser."""
import json
import argparse
import subprocess
import tempfile
import time
from pathlib import Path
from qa_scene import DevTools, chrome_path, websocket_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5500/?desktop=1')
    args = parser.parse_args()
    out = Path('qa_out')
    out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='karaokesesh-update-', ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen([str(chrome_path()), '--headless=new', '--no-first-run',
            '--remote-debugging-port=9232', '--remote-allow-origins=*', '--window-size=1480,940',
            f'--user-data-dir={profile}', args.url],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = DevTools(websocket_url(9232))
            time.sleep(3)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            dev.eval("document.getElementById('diagnosticsButton').click()")
            for _ in range(20):
                diagnostics = dev.eval("({open:document.getElementById('diagnosticsDialog').open,report:document.getElementById('diagnosticsOutput').textContent})")
                if 'KaraokeSesh: 0.4.4' in diagnostics['report']:
                    break
                time.sleep(.25)
            assert diagnostics['open'] and 'KaraokeSesh: 0.4.4' in diagnostics['report']
            assert 'GPU:' in diagnostics['report'] and 'Windows' in diagnostics['report']
            dev.shot('body').save(out / 'diagnostics-dialog.png')
            dev.eval("document.getElementById('diagnosticsClose').click()")
            dev.eval("document.getElementById('settingsButton').click()")
            for _ in range(20):
                update_panel = dev.eval("({open:document.getElementById('settingsDialog').open,version:document.getElementById('storeUpdateVersion').textContent,message:document.getElementById('storeUpdateMessage').textContent,disabled:document.getElementById('storeUpdateCheck').disabled})")
                if 'KaraokeSesh 0.4.4' in update_panel['version']:
                    break
                time.sleep(.25)
            assert update_panel['open'] and update_panel['disabled']
            assert 'local preview' in update_panel['message']
            assert dev.eval("fetch('/api/store-updates/check',{method:'POST'}).then(r=>r.status)") == 503
            dev.shot('body').save(out / 'store-updates-local.png')
            dev.eval("document.getElementById('settingsDialog').close()")
            dev.eval("window.qaErrors=[]; window.addEventListener('error',e=>qaErrors.push(e.message)); window.addEventListener('unhandledrejection',e=>qaErrors.push(String(e.reason)))")
            dev.eval("window.qaSet=(id,v)=>{const e=document.getElementById(id);e.value=v;e.dispatchEvent(new Event('input'));e.dispatchEvent(new Event('change'))}")
            trace = Path('qa/download-after/progress.json')
            if trace.exists():
                observed = []
                for entry in json.loads(trace.read_text(encoding='utf-8')):
                    if entry.get('phase') != 'model-download':
                        continue
                    job = {'phase':entry['phase'], 'downloaded_bytes':entry['downloadedBytes'],
                           'total_bytes':entry['totalBytes'], 'eta_seconds':entry.get('etaSeconds'), 'progress':entry['ratio']}
                    actual = dev.eval('(() => { updateTranscriptionProgress(' + json.dumps(job) + '); return parseInt(els.transcriptionPercent.value); })()')
                    expected = min(99, int(job['downloaded_bytes'] / job['total_bytes'] * 100 + .5))
                    assert actual == expected, (actual, expected)
                    observed.append(actual)
                assert len(set(observed)) > 5, observed
                print('Browser progress replay verified:', observed)
            dev.eval("qaSet('visualSelect','scene3d');qaSet('sceneArtStyle','storybook');qaSet('sceneDirection','left');qaSet('secondaryMotion','sway');qaSet('daytime','day');")
            assert dev.eval("project.background.artStyle==='storybook' && project.background.secondaryMotion==='sway'")
            time.sleep(1)
            dev.shot('body').save(out / 'studio-update.png')
            measurements = dev.eval("""(() => {
                window.qaOriginal=structuredClone(project);
                project.cues=Array.from({length:5000},(_,i)=>({id:'qa-'+i,start:i*2.88,end:i*2.88+2.4,text:'Long video cue '+i,words:[]}));
                selectedCueId='qa-0'; const start=performance.now(); renderCueList();
                const listMs=performance.now()-start;
                revealCueInList('qa-4999');
                return {listMs, cards:document.querySelectorAll('.cue-card').length,
                    lastAccessible:!!document.querySelector('[data-id="qa-4999"]')};
            })()""")
            assert measurements['cards'] == 100 and measurements['lastAccessible']
            dev.eval("project=structuredClone(qaOriginal);renderCueList();")
            performance_rows = []
            for direction in ['forward', 'up', 'down']:
                dev.eval("qaSet('sceneDirection'," + json.dumps(direction) + ");seekTo(0);virtualPlaying=false;togglePlay();")
                perf = dev.eval("""new Promise(resolve => {
                  const gaps=[];let lastPaint=lastInteractiveFrame;const started=performance.now();
                  function frame(now) {
                    if(lastInteractiveFrame!==lastPaint){gaps.push(lastInteractiveFrame-lastPaint);lastPaint=lastInteractiveFrame;}
                    if(now-started<2200)return requestAnimationFrame(frame);
                    gaps.shift();gaps.sort((a,b)=>a-b);
                    resolve({paintFps:gaps.length/(now-started)*1000,p95ms:gaps[Math.floor(gaps.length*.95)],maxMs:Math.max(...gaps)});
                  }requestAnimationFrame(frame);
                })""")
                dev.eval('virtualPlaying=false')
                performance_rows.append({'direction':direction, **perf})
            print('Interactive preview performance:', json.dumps(performance_rows))
            dev.eval("qaSet('sceneKit','ocean');qaSet('sunAzimuth',-30);qaSet('sunElevation',8);qaSet('moonAzimuth',35);qaSet('moonElevation',18);qaSet('oceanWaveStrength',80)")
            assert dev.eval("project.background.sceneKit==='ocean' && project.background.sunAzimuth===-30 && project.background.oceanWaveStrength===.8 && !document.getElementById('oceanControls').hidden")
            dev.eval('applyProjectToControls()')
            assert dev.eval("document.getElementById('sunElevation').value==='8'")
            dev.eval("qaSet('textSpace','scene');qaSet('text3DPitch',25);qaSet('text3DYaw',-20);qaSet('text3DRoll',8);applyProjectToControls()")
            assert dev.eval("project.style.text3DPitch===25 && document.getElementById('text3DYaw').value==='-20' && !document.getElementById('textOrientationControls').hidden")
            time.sleep(2)
            assert dev.eval("JSON.parse(localStorage.getItem(STORAGE_KEY)).style.text3DRoll===8")
            oriented_project = dev.eval('JSON.parse(JSON.stringify(project))')
            dev.eval('VFExport.prepare(640,360,' + json.dumps(oriented_project) + ')')
            orientation_cases = 0
            for kit in ['ocean','japan','italy','china','usa']:
                for direction in ['forward','left','right','up','down']:
                    dev.eval(f"project.background.sceneKit={json.dumps(kit)};project.background.sceneDirection={json.dumps(direction)}")
                    for _ in range(3):
                        dev.eval('VFExport.renderFrame(6,.1)')
                    assert dev.eval("(() => {const s=VFSceneGL.get(els.glCanvas);return s.textMeshes.size>0 && [...s.textMeshes.values()].every(m=>Number.isFinite(m.position.x+m.position.y+m.position.z) && Math.abs(m.quaternion.length()-1)<.00001)})()")
                    orientation_cases += 1
            dev.eval("project.background.sceneKit='ocean';project.background.sceneDirection='forward';VFExport.renderFrame(6,.1)")
            dev.shot('body').save(out / 'text-orientation.png')
            dev.eval("document.getElementById('resetTextOrientation').click()")
            assert dev.eval("project.style.text3DPitch===0 && project.style.text3DYaw===0 && project.style.text3DRoll===0")
            print('Orientation combinations:', orientation_cases)
            time.sleep(.4)
            dev.shot('body').save(out / 'ocean-studio.png')
            ocean_project = dev.eval('JSON.parse(JSON.stringify(project))')
            dev.eval('VFExport.prepare(640,360,' + json.dumps(ocean_project) + ')')
            for daytime in ['sunset','day','night']:
                dev.eval('project.background.daytime=' + json.dumps(daytime))
                frame = dev.eval('VFExport.renderFrame(6,.1)')
                assert frame['width']==640 and frame['height']==360
            # Every new camera/art combination must survive the actual export entrypoint.
            dev.eval("VFExport.prepare(640,360,qaOriginal)")
            for style in ['cinematic', 'storybook', 'psychedelic']:
                for direction in ['forward', 'left', 'right', 'up', 'down']:
                    dev.eval(f"project.background.artStyle={json.dumps(style)};project.background.sceneDirection={json.dumps(direction)}")
                    frame = dev.eval('VFExport.renderFrame(6,.1)')
                    assert frame['width'] == 640 and frame['height'] == 360, frame
            errors = dev.eval('qaErrors')
            assert not errors, errors
            assert not dev.eval('Boolean(window.__visualErrorShown)')
            print(json.dumps({'cueList':measurements,'exportCombinations':18,'oceanControls':True,'errors':errors,
                'screenshot':str((out / 'studio-update.png').resolve())}))
        finally:
            if dev:
                dev.close()
            browser.terminate()
            browser.wait(timeout=15)


if __name__ == '__main__':
    main()
