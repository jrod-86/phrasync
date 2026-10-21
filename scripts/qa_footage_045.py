"""Exercise real mixed media import/edit/export in an isolated editor."""
import copy
import io
import json
import subprocess
import tempfile
import time
import wave
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from qa_scene import DevTools, chrome_path, websocket_url
from karaokesesh.storage import store_path, delete_asset
from karaokesesh.renderer import render_project
from karaokesesh.media import run_ffmpeg, decode_test


def main():
    origin = "http://127.0.0.1:5514"
    out = Path("qa_out/footage-045"); out.mkdir(parents=True, exist_ok=True)
    assets = []
    with tempfile.TemporaryDirectory(prefix="karaokesesh-footage-qa-", ignore_cleanup_errors=True) as folder:
        folder = Path(folder)
        red = folder / "red.png"; blue = folder / "blue.png"; video = folder / "test.mp4"; audio = folder / "song.wav"
        Image.new("RGB", (640, 360), "red").save(red)
        Image.new("RGB", (640, 360), "blue").save(blue)
        run_ffmpeg(["-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=25:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)])
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1); handle.setsampwidth(2); handle.setframerate(16000)
            handle.writeframes((np.sin(np.arange(19200) * 2*np.pi*440/16000) * 8000).astype(np.int16).tobytes())
        song = store_path("audio", audio); assets.append(song.id)
        browser = subprocess.Popen([str(chrome_path()), "--headless=new", "--no-first-run", "--mute-audio", "--remote-debugging-port=9238", "--remote-allow-origins=*", "--window-size=1480,1000", f"--user-data-dir={folder / 'profile'}", origin + "/?desktop=1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = DevTools(websocket_url(9238)); time.sleep(2)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close());window.qaErrors=[];window.addEventListener('error',e=>qaErrors.push(e.message));window.addEventListener('unhandledrejection',e=>qaErrors.push(String(e.reason)));document.getElementById('footageSection').open=true")
            root = dev.call("DOM.getDocument")["root"]["nodeId"]
            node = dev.call("DOM.querySelector", {"nodeId": root, "selector": "#footageInput"})["nodeId"]
            dev.call("DOM.setFileInputFiles", {"nodeId": node, "files": [str(red.resolve()), str(video.resolve()), str(blue.resolve())]})
            for _ in range(100):
                if dev.eval("project.background.mediaLibrary.length") == 3: break
                time.sleep(.1)
            project = dev.eval("project")
            assets.extend(a["id"] for a in project["background"]["mediaLibrary"])
            assert len(project["background"]["mediaLibrary"]) == 3, dev.eval("els.assetStatus.textContent")
            assert len(project["background"]["clips"]) == 0, "Import must not modify the edit"
            assert dev.eval("document.querySelectorAll('.media-card[draggable]').length") == 3
            # Use the browser's actual drag/drop handlers, placing all imported media.
            dev.eval("project.background.mediaLibrary.forEach((a,i)=>{const dt=new DataTransfer();dt.setData('application/x-karaokesesh-media',a.id);const lane=document.getElementById('footageLane');lane.dispatchEvent(new DragEvent('drop',{dataTransfer:dt,clientX:lane.getBoundingClientRect().left+i*30,bubbles:true,cancelable:true}));})")
            assert dev.eval("project.background.clips.length") == 3
            assert dev.eval("project.background.footageEnabled")
            dev.eval("project.cues=[{id:'test',start:0,end:1.2,text:'MEDIA TEST',manual:true}];project.duration=1.2;project.canvas={width:640,height:360,fps:25,aspect:'16:9'};project.audioAssetId=" + json.dumps(song.id) + ";project.audio=" + json.dumps({"id": song.id,"url": song.url,"duration":1.2,"name":"QA tone"}) + ";project.background.clips.forEach((c,i)=>{c.start=i*.4;c.end=(i+1)*.4;c.in=i===1?.2:0;c.rate=1;c.zoomStart=1.2;c.zoomEnd=1.4;c.xStart=-1;c.xEnd=1});project.background.effects={bw:100,pendulum:3,shake:1,flash:4,gradient:20,particles:20,spectrum:70,bpm:120,color1:'#7c3aed',color2:'#db2777'};project.export={crf:28,preset:'ultrafast',bitrateMbps:50};applyProjectToControls();timeline.fitAll();refreshFootageControls()")
            assert dev.eval("document.querySelectorAll('.footage-block').length") == 3
            # Change trim through the actual inspector and verify project persistence.
            dev.eval("document.getElementById('footageSelect').value=project.background.clips[1].id;document.getElementById('footageSelect').dispatchEvent(new Event('change'));document.getElementById('clip-in').value='.1';document.getElementById('clip-in').dispatchEvent(new Event('change'))")
            assert dev.eval("project.background.clips[1].in") == .1
            dev.eval("document.getElementById('clip-xStart-slider').value='-.5';document.getElementById('clip-xStart-slider').dispatchEvent(new Event('input',{bubbles:true}));document.getElementById('fx-gradient-slider').value='25';document.getElementById('fx-gradient-slider').dispatchEvent(new Event('input',{bubbles:true}))")
            assert dev.eval("selectedFootage().xStart===-.5 && project.background.effects.gradient===25")
            assert dev.eval("!document.getElementById('footageTools').hidden")
            # Zoom anchors the real playhead, even after navigating away from it.
            dev.eval("seekTo(.6);timeline.setView(0,.8);document.getElementById('zoomInButton').click()")
            assert dev.eval("Math.abs(timeline.xToTime(timeline.width/2)-(.6-project.timing.offset))<.002")
            dev.eval("document.getElementById('zoomOutButton').click()")
            assert dev.eval("Math.abs(timeline.xToTime(timeline.width/2)-(.6-project.timing.offset))<.002")
            dev.eval("timeline.fitAll();window.qaClip=selectedFootageId;const b=document.querySelector('.footage-block[data-id=\"'+qaClip+'\"]');const r=b.getBoundingClientRect();b.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:r.left+10,clientY:r.top+10}))")
            assert dev.eval("!document.getElementById('clipContextMenu').hidden")
            dev.eval("const inputs=document.querySelectorAll('#clipContextMenu input[type=range]');inputs[1].value='1.3';inputs[1].dispatchEvent(new Event('input'))")
            assert dev.eval("selectedFootage().zoomStart===1.3 && selectedFootage().zoomEnd===1.3")
            dev.eval("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))")
            assert dev.eval("document.getElementById('clipContextMenu').hidden")
            assert dev.eval("document.querySelector('#projectMenu #saveProjectButton')!==null")
            assert dev.eval("document.querySelectorAll('.author-links a[data-external]').length") == 5
            assert dev.eval("JSON.stringify(migrateProject(clone(project)).background.mediaLibrary)===JSON.stringify(project.background.mediaLibrary)")
            assert dev.eval("migrateProject(JSON.parse(JSON.stringify(project))).background.clips.length") == 3
            dev.eval("document.getElementById('footageDuplicate').click()")
            assert dev.eval("project.background.clips.length") == 4
            dev.eval("document.getElementById('footageRemove').click()")
            assert dev.eval("project.background.clips.length") == 3
            dev.eval("window.qaClips=clone(project.background.clips);selectedFootageId=project.background.clips[1].id;refreshFootageControls();seekTo(.6);document.getElementById('footageSplit').click()")
            assert dev.eval("project.background.clips.length===4 && Math.abs(selectedFootage().in-.3)<.002"), "Split did not preserve the source timeline"
            dev.eval("project.background.clips=qaClips;refreshFootageControls();footageChanged()")
            for t in [.1, .6, 1.0]:
                dev.eval(f"seekTo({t})"); time.sleep(.5)
                assert dev.eval("!document.getElementById('footageCanvas').hidden")
            dev.shot("body").save(out / "editor.png")
            assert dev.eval("qaErrors") == [], dev.eval("qaErrors")
            # Switching back to a legacy background keeps imported clips, but disables their override.
            dev.eval("document.querySelector('#backgroundType button[data-value=\"dynamic\"]').click()")
            assert dev.eval("!project.background.footageEnabled && project.background.clips.length===3")
            dev.eval("document.getElementById('footageEnable').checked=true;document.getElementById('footageEnable').dispatchEvent(new Event('change'));seekTo(0);timeline.fitAll();timeline.follow=false")
            # Use real pointer events to move the first clip and trim its right edge.
            block = dev.eval("(() => {const r=document.querySelector('.footage-block').getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+15}})()")
            for kind, x in [("mousePressed", block["x"]), ("mouseMoved", block["x"]+30), ("mouseReleased", block["x"]+30)]:
                dev.call("Input.dispatchMouseEvent", {"type":kind,"x":x,"y":block["y"],"button":"left","buttons":0 if kind=="mouseReleased" else 1,"clickCount":1})
            assert dev.eval("project.background.clips[0].start>0"), "Clip dragging did not move the clip"
            dev.eval("project.background.clips[0].start=0;project.background.clips[0].end=.4;refreshFootageControls();footageChanged()")
            project = dev.eval("project"); project["__renderOrigin"] = origin
            result = render_project(project, out / "mixed-effects.mp4")
            assert result["frames"] == 30 and decode_test(out / "mixed-effects.mp4")[0]
            sound = run_ffmpeg(["-v","error","-i",str(out / "mixed-effects.mp4"),"-map","0:a:0","-f","null","-"])
            for t in [.1, .6, 1.0]:
                shot = run_ffmpeg(["-ss",str(t),"-i",str(out / "mixed-effects.mp4"),"-frames:v","1","-f","image2pipe","-vcodec","png","pipe:1"])
                Image.open(io.BytesIO(shot.stdout)).save(out / f"frame-{t}.png")
            assert not list(out.glob("*.partial.*"))
            three = copy.deepcopy(project); three["background"]["textSpace"] = "scene"
            three["cues"] = [{"id":"test","start":0,"end":1.2,"text":"3D MEDIA","manual":True}]
            three_result = render_project(three, out / "mixed-effects-3d-text.mp4")
            assert three_result["frames"] == 30 and decode_test(out / "mixed-effects-3d-text.mp4")[0]
            three_shot = run_ffmpeg(["-ss","0.6","-i",str(out / "mixed-effects-3d-text.mp4"),"-frames:v","1","-f","image2pipe","-vcodec","png","pipe:1"])
            Image.open(io.BytesIO(three_shot.stdout)).save(out / "3d-text.png")
            comparison = copy.deepcopy(three); comparison["cues"] = []
            render_project(comparison, out / "background-only.mp4")
            no_text = run_ffmpeg(["-ss","0.6","-i",str(out / "background-only.mp4"),"-frames:v","1","-f","image2pipe","-vcodec","png","pipe:1"])
            text_pixels = np.asarray(Image.open(io.BytesIO(three_shot.stdout)).convert("RGB"), dtype=float)
            plain_pixels = np.asarray(Image.open(io.BytesIO(no_text.stdout)).convert("RGB"), dtype=float)
            assert np.abs(text_pixels - plain_pixels).mean() > .5, "3D text disappeared during asynchronous video seek"
            dev.eval("seekTo(0);togglePlay()")
            perf = dev.eval("""new Promise(resolve=>{const gaps=[];const begin=performance.now();let last=lastInteractiveFrame;
              function step(now){if(lastInteractiveFrame!==last){gaps.push(lastInteractiveFrame-last);last=lastInteractiveFrame;}
                if(now-begin<650){requestAnimationFrame(step);return;}gaps.shift();gaps.sort((a,b)=>a-b);
                resolve({paintFps:gaps.length/(now-begin)*1000,p95:gaps[Math.floor(gaps.length*.95)]});}requestAnimationFrame(step);})""")
            print("Preview performance: " + json.dumps(perf), flush=True)
            dev.eval("els.audioPlayer.pause();virtualPlaying=false;seekTo(.6);timeline.fitAll();document.getElementById('footageSection').open=true;document.getElementById('footageSection').scrollIntoView({block:'start'})")
            dev.shot("body").save(out / "editor.png")
            # Integrated 2D and 3D worlds are clip sources, not mutually exclusive backgrounds.
            dev.eval("window.qaBase=clone(project);project.background.tracks=['V1','V2'];project.background.clips=project.background.clips.slice(0,1);project.background.clips[0].start=0;project.background.clips[0].end=1.2;project.background.clips[0].track=0;project.background.effects={drop:10,pulse:10,bpm:120};project.cues=[{id:'creative',start:0,end:1.2,text:'SPIRAL WORD FIELD',manual:true}]")
            for visual in ["aurora", "particles", "equalizer", "grid", "scene", "scene3d"]:
                dev.eval("project.background.visual="+json.dumps(visual)+";project.background.sceneKit='ocean';document.getElementById('addVisualClip').click();window.qaVisual=project.background.mediaLibrary.at(-1);project.background.clips=project.background.clips.slice(0,1);addMediaClip(qaVisual.id,0,1);selectedFootage().end=1.2;selectedFootage().opacity=.6;selectedFootage().transition='fade';selectedFootage().fadeIn=.2;project.style.preset='spiral';project.background.textSpace='flat';applyProjectToControls();seekTo(.6)")
                time.sleep(.5)
                assert dev.eval("qaErrors") == [], dev.eval("qaErrors")
                exported = dev.eval("project")
                exported["__renderOrigin"] = origin
                rendered = render_project(exported, out / f"layer-{visual}.mp4")
                assert decode_test(out / f"layer-{visual}.mp4")[0]
                shot = run_ffmpeg(["-ss","0.6","-i",str(out / f"layer-{visual}.mp4"),"-frames:v","1","-f","image2pipe","-vcodec","png","pipe:1"])
                (out / f"layer-{visual}.png").write_bytes(shot.stdout)
                print("PASS layered visual + spiral MP4: " + visual, flush=True)
            for preset in ["spiral","constellation"]:
                dev.eval("project.style.preset="+json.dumps(preset)+";project.background.textSpace='scene';applyProjectToControls();seekTo(.6)")
                time.sleep(.5)
                assert dev.eval("qaErrors") == [], dev.eval("qaErrors")
                exported = dev.eval("project"); exported["__renderOrigin"] = origin
                assert decode_test(Path(render_project(exported,out / f"layer-3d-{preset}.mp4")["path"]))[0]
                dev.shot("body").save(out / f"layer-3d-{preset}-editor.png")
                shot=run_ffmpeg(["-ss","0.6","-i",str(out / f"layer-3d-{preset}.mp4"),"-frames:v","1","-f","image2pipe","-vcodec","png","pipe:1"])
                (out / f"layer-3d-{preset}.png").write_bytes(shot.stdout)
            for transition in ["wipe","slide"]:
                dev.eval("project.background.textSpace='flat';project.background.clips[1].transition="+json.dumps(transition)+";project.background.clips[1].fadeIn=.8;project.style.preset='constellation';applyProjectToControls();seekTo(.4)")
                exported = dev.eval("project"); exported["__renderOrigin"] = origin
                assert decode_test(Path(render_project(exported,out / f"transition-{transition}.mp4")["path"]))[0]
                print("PASS MP4 transition: " + transition, flush=True)
            dev.eval("project=qaBase;applyProjectToControls();document.getElementById('onboardingHide').checked=true;document.getElementById('onboardingContinue').click()")
            assert dev.eval("localStorage.getItem(ONBOARDING_KEY)") == "hidden"
            dev.eval("document.getElementById('onboardingHide').checked=false;document.getElementById('onboardingContinue').click()")
            assert dev.eval("localStorage.getItem(ONBOARDING_KEY)") is None
            print("PASS: real multi-file import, trim, mixed image/video clips, duplicate/remove, project migration, all effects, audio and MP4 export", flush=True)
            print(json.dumps(result), flush=True)
        finally:
            if dev: dev.close()
            browser.terminate(); browser.wait(timeout=10)
            for asset in set(assets): delete_asset(asset)


if __name__ == "__main__": main()
