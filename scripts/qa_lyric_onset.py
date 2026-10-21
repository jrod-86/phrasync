"""Capture actual glyph pixels against an audio fixture with a known onset."""
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
import wave

from qa_scene import DevTools, chrome_path, websocket_url
from karaokesesh.media import ffmpeg_exe


def main():
    out = Path('qa_out')
    with wave.open(str(out / 'timing-speech-source.wav')) as wav:
        rate = wav.getframerate()
        assert wav.getsampwidth() == 2
        speech = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').astype(float) / 32768
        speech = speech.reshape(-1, wav.getnchannels()).mean(axis=1)
    active = np.flatnonzero(np.abs(speech) > .002)
    speech = speech[active[0]:active[-1] + 1]
    fixture = np.concatenate([np.zeros(rate), speech, np.zeros(rate)])
    with wave.open(str(out / 'timing-known-onset.wav'), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(rate)
        wav.writeframes((fixture * 32767).astype('<i2').tobytes())
    first_audible = float(np.flatnonzero(np.abs(fixture) > .002)[0] / rate)
    assert first_audible == 1
    original = Path('C:/Users/w4k3/.karaokesesh/projects/I_Still_Wait.verseframe.json')
    song_project = json.loads(original.read_text(encoding='utf-8'))
    song = Path('C:/Users/w4k3/.karaokesesh/uploads') / song_project['audioAssetId']
    subprocess.run([ffmpeg_exe(), '-y', '-ss', '11.8', '-i', str(song), '-t', '7',
                    str(out / 'timing-original-song.wav')], check=True, capture_output=True)
    with tempfile.TemporaryDirectory(prefix='karaokesesh-onset-', ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen([str(chrome_path()), '--headless=new', '--no-first-run',
            '--remote-debugging-port=9236', '--remote-allow-origins=*', '--window-size=960,620',
            f'--user-data-dir={profile}', 'http://127.0.0.1:5510/?desktop=1'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = DevTools(websocket_url(9236)); time.sleep(2)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            dev.eval("window.qaBase=structuredClone(DEFAULT_PROJECT);qaBase.background.type='color';qaBase.background.backgroundColor='#080812';qaBase.style.beatReact=false;qaBase.style.fontSize=68;qaBase.style.wordLead=.5;qaBase.timing.offset=0;qaBase.cues=[{id:'onset',start:1,end:3,text:'KaraokeSesh makes words move.',words:[{text:'KaraokeSesh',start:1,end:1.5},{text:'makes',start:1.5,end:1.9},{text:'words',start:1.9,end:2.4},{text:'move.',start:2.4,end:3}]}]")
            presets = dev.eval('VFKinetic.PRESET_ORDER')
            rows, records = [], []
            for space in ['screen', 'scene']:
                for preset in presets:
                    dev.eval(f"qaBase.background.textSpace={json.dumps(space)};qaBase.style.preset={json.dumps(preset)};VFExport.prepare(640,360,qaBase)")
                    dev.eval('project.cues=[];VFExport.renderFrame(.999,0)')
                    blank = dev.shot('#stage')
                    dev.eval('project.cues=structuredClone(qaBase.cues);VFExport.renderFrame(.999,0)')
                    before = dev.shot('#stage')
                    early = int(np.max(np.abs(np.asarray(before).astype(int) - np.asarray(blank).astype(int))))
                    dev.eval('VFExport.renderFrame(1.12,0)')
                    after = dev.shot('#stage')
                    changed = int(np.count_nonzero(np.max(np.abs(np.asarray(after).astype(int) - np.asarray(blank).astype(int)), axis=2) > 10))
                    assert early == 0, (space, preset, 'early pixels', early)
                    assert changed > 5, (space, preset, 'missing glyph', changed)
                    records.append({'space': space, 'preset': preset, 'preOnsetPixelDelta': early, 'postOnsetChangedPixels': changed})
                    row = Image.new('RGB', (640, 205), '#161622')
                    row.paste(before.resize((320,180)), (0,25)); row.paste(after.resize((320,180)), (320,25))
                    ImageDraw.Draw(row).text((8,6), f'{space} / {preset}   BEFORE 0.999s | AFTER 1.120s', fill='white')
                    rows.append(row)
            sheet = Image.new('RGB', (640, len(rows)*205))
            for index, row in enumerate(rows): sheet.paste(row, (0,index*205))
            sheet.save(out / 'timing-onset-contact-sheet.png')
            # Listen-and-watch fixtures: sampled stage frames with the original audio.
            samples = [
                ('known', None, 0., len(fixture)/rate, out / 'timing-known-onset.wav'),
                ('original', song_project, 11.8, 7., out / 'timing-original-song.wav')]
            for name, source, start, length, audio in samples:
                if source:
                    source['background'] = {**source.get('background', {}), 'type': 'color', 'backgroundColor': '#080812', 'textSpace': 'screen'}
                    dev.eval(f'VFExport.prepare(640,360,{json.dumps(source)})')
                else:
                    dev.eval("qaBase.background.textSpace='screen';qaBase.style.preset='kinetic-slam';VFExport.prepare(640,360,qaBase)")
                video = out / f'timing-{name}-audiovisual.mp4'
                encoder = subprocess.Popen([ffmpeg_exe(), '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
                    '-s', '640x360', '-r', '12', '-i', '-', '-i', str(audio), '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(video)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                for frame in range(int(length*12)):
                    t = start + frame/12
                    dev.eval(f'VFExport.renderFrame({t},0)')
                    shot = dev.shot('#stage')
                    ImageDraw.Draw(shot).text((8,8), f'Audio time {t:.3f}s', fill='white')
                    encoder.stdin.write(shot.tobytes())
                encoder.stdin.close(); assert encoder.wait(timeout=30) == 0
            report = {'audioOnsetSeconds': first_audible, 'knownFixture': str(out / 'timing-known-audiovisual.mp4'),
                      'originalFirstWordStart': song_project['cues'][0]['start'], 'matrix': records}
            (out / 'timing-onset-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report))
        finally:
            if dev: dev.close()
            browser.terminate(); browser.wait(timeout=15)


if __name__ == '__main__':
    main()
