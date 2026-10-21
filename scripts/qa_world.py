"""Isolated renderer contact sheet and deterministic-scrub smoke test."""
import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw
from qa_scene import DevTools, chrome_path, websocket_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='qa_out/world-review.jpg')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='karaokesesh-world-') as profile:
        server = subprocess.Popen([sys.executable, '-m', 'http.server', '5591', '--bind', '127.0.0.1'],
                                  cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = subprocess.Popen([str(chrome_path()), '--headless=new', '--no-first-run',
            '--remote-debugging-port=9231', '--remote-allow-origins=*', '--window-size=960,620',
            f'--user-data-dir={profile}', 'http://127.0.0.1:5591/'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = DevTools(websocket_url(9231))
            time.sleep(.7)
            dev.call('Page.navigate', {'url': 'http://127.0.0.1:5591/'})
            time.sleep(.7)
            dev.eval("""(async () => {
              document.body.innerHTML = '<canvas id="world"></canvas>';
              document.body.style.margin = '0';
              document.body.style.overflow = 'hidden';
              await import('/static/scene3d-gl.js');
              window.testWorld = VFSceneGL.get(document.querySelector('canvas'));
              testWorld.setSize(960, 540); testWorld.build('japan');
            })()""")
            cases = [('cinematic', 'forward'), ('storybook', 'forward'), ('psychedelic', 'forward'),
                     ('cinematic', 'left'), ('storybook', 'up'), ('psychedelic', 'right'),
                     ('cinematic','down'),('storybook','down'),('psychedelic','down')]
            sheet = Image.new('RGB', (1440, 870), '#17191e')
            draw = ImageDraw.Draw(sheet)
            report = []
            for i, (style, direction) in enumerate(cases):
                opts = {'artStyle': style, 'direction': direction, 'secondaryMotion': 'sway',
                        'environment': {'daytime': 'day' if style == 'storybook' else 'sunset',
                                        'season': 'summer', 'weather': 'clear'}}
                expr = f'testWorld.update(7.25, {json.dumps(opts)}); testWorld.render();'
                dev.eval(expr)
                shot = dev.shot('#world').resize((480, 270))
                sheet.paste(shot, ((i % 3) * 480, (i // 3) * 290))
                draw.text(((i % 3) * 480 + 10, (i // 3) * 290 + 273), f'{style} / {direction}', fill='white')
                before = dev.eval('testWorld.world.batches.cliffs.instanceMatrix.array.slice(0, 32).join()')
                dev.eval('testWorld.update(29);' + expr)
                after = dev.eval('testWorld.world.batches.cliffs.instanceMatrix.array.slice(0, 32).join()')
                assert before == after, (style, direction, 'scrub changed scenery')
                report.append(dev.eval('({drawCalls:testWorld.renderer.info.render.calls, triangles:testWorld.renderer.info.render.triangles})'))
            sheet.save(out)
            print(json.dumps({'image': str(out), 'cases': report, 'deterministic': True}))
        finally:
            if dev:
                dev.close()
            browser.terminate(); server.terminate()
            browser.wait(timeout=15); server.wait(timeout=15)
            time.sleep(.5)


if __name__ == '__main__':
    main()
