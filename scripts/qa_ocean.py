"""Independent ocean pixels, switching, deterministic export and frame-cost QA."""
import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from qa_scene import DevTools, chrome_path, websocket_url
from websockets.sync.client import connect


class OceanTools(DevTools):
    def __init__(self, url):
        self.socket = connect(url, origin='http://localhost:9237', max_size=32_000_000)
        self.counter = 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5510')
    parser.add_argument('--out', default='qa_out/ocean-review')
    args = parser.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='karaokesesh-ocean-qa-', ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen([str(chrome_path()), '--headless=new', '--no-first-run',
            '--remote-debugging-port=9237', '--remote-allow-origins=*', '--window-size=1280,800',
            f'--user-data-dir={profile}', args.url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = OceanTools(websocket_url(9237)); time.sleep(2)
            dev.eval("""(async () => {
                window.qaErrors=[]; addEventListener('error',e=>qaErrors.push(e.error?.stack||e.message));
                addEventListener('unhandledrejection',e=>qaErrors.push(String(e.reason)));
                window.__vfExportMode=true;
                document.body.innerHTML='<canvas id="oceanQa"></canvas>';
                document.body.style.cssText='margin:0;overflow:hidden;background:black';
                await import('/static/scene3d-gl.js');
                window.qaScene=VFSceneGL.get(document.querySelector('canvas'));
                qaScene.setSize(1280,720); qaScene.build('ocean');
                window.qaOptions={direction:'forward',seed:1337,speed:9,pulse:0,density:1,
                  artStyle:'cinematic',secondaryMotion:'none',waveStrength:.65,
                  sunAzimuth:25,sunElevation:12,moonAzimuth:-25,moonElevation:18,
                  environment:{daytime:'sunset',weather:'clear',season:'summer'}};
                window.qaFrame=(t,patch={})=>{
                  qaOptions={...qaOptions,...patch,environment:{...qaOptions.environment,...patch.environment}};
                  qaScene.update(t,qaOptions);qaScene.render();
                };
            })()""")
            cases = [
                ('sunset', {'environment': {'daytime':'sunset'}, 'sunAzimuth':25,'sunElevation':12}),
                ('day', {'environment': {'daytime':'day'}, 'sunAzimuth':15,'sunElevation':45}),
                ('night', {'environment': {'daytime':'night'}, 'moonAzimuth':-25,'moonElevation':18}),
                ('sun-left', {'environment': {'daytime':'sunset'}, 'sunAzimuth':-40,'sunElevation':12}),
                ('sun-right', {'environment': {'daytime':'sunset'}, 'sunAzimuth':40,'sunElevation':12}),
                ('sun-high', {'environment': {'daytime':'sunset'}, 'sunAzimuth':0,'sunElevation':50}),
                ('moon-left', {'environment': {'daytime':'night'}, 'moonAzimuth':-40,'moonElevation':18}),
                ('moon-right', {'environment': {'daytime':'night'}, 'moonAzimuth':40,'moonElevation':18}),
            ]
            images = {}; metrics = []
            for name, patch in cases:
                dev.eval(f'qaFrame(9.25,{json.dumps(patch)})')
                # Warm all materials before deterministic screenshot comparison.
                dev.eval('qaScene.render()'); time.sleep(.08)
                first = dev.shot('#oceanQa'); first.save(out / f'{name}.png'); images[name] = first
                dev.eval('qaFrame(41);qaFrame(9.25)')
                repeat = dev.shot('#oceanQa')
                diff = np.abs(np.asarray(first).astype(int)-np.asarray(repeat).astype(int))
                metrics.append({'case':name,'repeatMaxPixelDelta':int(diff.max())})
                assert diff.max() == 0, (name, 'time scrub changed render')
            controls = {}
            for a,b in [('sun-left','sun-right'),('moon-left','moon-right'),('day','night')]:
                controls[f'{a}:{b}'] = float(np.abs(np.asarray(images[a]).astype(float)-np.asarray(images[b]).astype(float)).mean())
                assert controls[f'{a}:{b}'] > .1, (a,b,'controls had no visible effect')
            sheet = Image.new('RGB',(1280,4*385),'#12141c')
            draw = ImageDraw.Draw(sheet)
            for i,(name,_) in enumerate(cases):
                x,y=i%2*640,i//2*385
                sheet.paste(images[name].resize((640,360)),(x,y));draw.text((x+10,y+363),name,fill='white')
            sheet.save(out/'contact-sheet.jpg',quality=94)
            performance = dev.eval("""(() => {
                const times=[];const gl=qaScene.renderer.getContext();const pixel=new Uint8Array(4);
                for(let i=0;i<90;i++){const a=performance.now();qaFrame(9+i/30);gl.finish();gl.readPixels(0,0,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);if(i>=15)times.push(performance.now()-a);}
                times.sort((a,b)=>a-b);const ext=gl.getExtension('WEBGL_debug_renderer_info');
                return {medianMs:times[Math.floor(times.length*.5)],p95Ms:times[Math.floor(times.length*.95)],
                  drawCalls:qaScene.renderer.info.render.calls,triangles:qaScene.renderer.info.render.triangles,
                  gpu:ext?gl.getParameter(ext.UNMASKED_RENDERER_WEBGL):null};
            })()""")
            memory=[]
            for cycle in range(6):
                dev.eval("qaScene.build('usa');qaFrame(9.25)")
                dev.eval("qaScene.build('ocean');qaFrame(9.25)")
                time.sleep(.1)
                memory.append(dev.eval('({...qaScene.renderer.info.memory,programs:qaScene.renderer.info.programs.length})'))
            # GPU internal shared resources can persist; repeated scenes cannot grow without bound.
            assert memory[-1]['geometries'] <= memory[1]['geometries'] + 2, memory
            assert memory[-1]['textures'] <= memory[1]['textures'] + 2, memory
            errors=dev.eval('qaErrors')
            report={'cases':metrics,'controlPixelDifferences':controls,'performance':performance,
                    'switchingMemory':memory,'errors':errors,'note':'Independent WebGL renderer at1280x720; synchronous pixel readback forces GPU work to complete and adds readback overhead, not a packaged-app FPS guarantee.'}
            (out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(report))
            assert not errors, errors
        finally:
            if dev:dev.close()
            browser.terminate();browser.wait(timeout=15)


if __name__=='__main__':main()
