"""Isolated browser regression checks for the local 0.4.5 editor preview."""
import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path

from qa_scene import DevTools, chrome_path, websocket_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5505/?desktop=1")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="karaokesesh-045-qa-", ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen([
            str(chrome_path()), "--headless=new", "--no-first-run",
            "--remote-debugging-port=9236", "--remote-allow-origins=*",
            "--window-size=1480,940", f"--user-data-dir={profile}", args.url,
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = DevTools(websocket_url(9236))
            time.sleep(2)
            assert dev.eval("typeof timeline") == "object"
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close());window.qaErrors=[];window.addEventListener('error',e=>qaErrors.push(e.message));window.addEventListener('unhandledrejection',e=>qaErrors.push(String(e.reason)))")
            dev.eval("project.cues=Array.from({length:60},(_,i)=>({id:'test-'+i,start:i*3,end:i*3+2,text:'Lyric '+i,words:[]}));project.audio=null;project.audioAssetId=null;selectedCueId='test-20';renderCueList();updateDurationUI();els.cueList.scrollTop=400;window.qaScroll=els.cueList.scrollTop;els.addCueButton.click()")
            time.sleep(.2)
            assert dev.eval("Math.abs(els.cueList.scrollTop-qaScroll)<2"), "Add cue changed scroll position"
            dev.eval("selectedCueId='test-20';const c=project.cues.find(c=>c.id===selectedCueId);c.words=[{text:c.text,start:c.start,end:c.end}];window.qaSource=structuredClone(c);renderCueList();document.querySelector('[data-id=\"test-20\"] .cue-duplicate').click()")
            result = dev.eval("({copy:project.cues.find(c=>c.id===selectedCueId),source:project.cues.find(c=>c.id==='test-20'),focused:document.activeElement.className})")
            assert result["copy"]["start"] == result["source"]["end"]
            assert result["copy"]["words"][0]["start"] == result["copy"]["start"]
            assert result["copy"]["manual"] and result["focused"] == "cue-text"
            assert dev.eval("project.cues.find(c=>c.id==='test-20').words !== project.cues.find(c=>c.id===selectedCueId).words")
            dev.eval("document.activeElement.blur();timeline.follow=false;timeline.setView(30,12);window.qaCues=JSON.stringify(project.cues);window.qaSeek=lyricTime()")
            rect = dev.eval("(() => {const r=els.timelineCanvas.getBoundingClientRect();return {x:r.x+400,y:r.y+100}})()")
            assert dev.eval(f"document.elementFromPoint({rect['x']},{rect['y']})?.id") == "timelineCanvas", "Timeline is covered by another control"
            dev.call("Input.dispatchMouseEvent", {"type": "mousePressed", "button": "middle", "buttons": 4, "clickCount": 1, **rect})
            dev.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "button": "middle", "buttons": 4, "x": rect["x"] - 180, "y": rect["y"]})
            dev.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "button": "middle", "buttons": 0, "clickCount": 1, "x": rect["x"] - 180, "y": rect["y"]})
            pan = dev.eval("({start:timeline.viewStart,unchanged:JSON.stringify(project.cues)===qaCues,time:lyricTime(),before:qaSeek,drag:timeline.drag?.type,rect:els.timelineCanvas.getBoundingClientRect().toJSON()})")
            assert pan["start"] > 30 and pan["unchanged"] and pan["time"] == pan["before"] and not pan.get("drag"), pan
            dev.eval("document.getElementById('timelineScroll').scrollLeft+=120")
            time.sleep(.2)
            assert dev.eval("timeline.viewStart>32 && !timeline.follow")
            # Test bridge routing; real Windows dialogs are covered by Python tests and user review.
            dev.eval("window.qaSaves=[];window.pywebview={api:{save_text_file:async(...args)=>{qaSaves.push(args);return 'C:/chosen/'+args[1]},load_project_file:async()=>({content:JSON.stringify({...project,title:'Native load test'})})}};els.saveProjectButton.click()")
            time.sleep(.2)
            assert dev.eval("qaSaves.length===1 && qaSaves[0][2]==='json' && JSON.parse(qaSaves[0][0]).cues.length===project.cues.length")
            dev.eval("els.loadProjectButton.click()")
            time.sleep(.2)
            assert dev.eval("project.title==='Native load test'")
            for fmt in ["srt", "vtt", "ass", "lrc", "elrc"]:
                count = dev.eval("qaSaves.length")
                dev.eval(f"els.exportFormat.value={json.dumps(fmt)};els.exportSrtButton.click()")
                for _ in range(30):
                    last = dev.eval("qaSaves.at(-1)")
                    if dev.eval("qaSaves.length") > count:
                        break
                    time.sleep(.1)
                assert dev.eval("qaSaves.length") == count + 1
                last = dev.eval("qaSaves.at(-1)")
                assert last[2] == ("lrc" if fmt == "elrc" else fmt), last
                assert last[0], "Export has no content"
            dev.eval("els.toastStack.textContent='';window.pywebview.api.save_text_file=async()=>null;els.exportSrtButton.click()")
            time.sleep(.4)
            assert dev.eval("els.toastStack.textContent===''"), "Cancelled export reported success"
            assert dev.eval("qaErrors") == [], dev.eval("qaErrors")
            # A folder is mandatory, the custom rate survives project save/load,
            # double clicks cannot queue two jobs, and showing a result cannot copy it.
            dev.eval("els.rateControlSelect.value='bitrate';els.rateControlSelect.dispatchEvent(new Event('change'));els.bitrateInput.value='150';els.bitrateInput.dispatchEvent(new Event('input'))")
            assert dev.eval("project.export.bitrateMbps===150 && !els.bitrateField.hidden && els.qualitySelect.disabled")
            dev.eval("window.qaRequests=0;window.qaOldApi=api;api=async(path)=>{if(path==='/api/render'){qaRequests++;await new Promise(r=>setTimeout(r,100));throw new Error('QA request intercepted');}return qaOldApi(path)};selectedRenderDirectory=null;els.toastStack.textContent='';startRender()")
            time.sleep(.1)
            assert dev.eval("qaRequests===0 && els.toastStack.textContent.includes('Choose')")
            dev.eval("(async()=>{window.pywebview.api.choose_render_directory=async()=> 'C:/chosen';window.pywebview.api.get_selected_render_directory=async()=>selectedRenderDirectory;await chooseRenderDirectory();startRender();startRender()})()")
            time.sleep(.2)
            assert dev.eval("qaRequests===1 && !renderStarting && !currentRenderJob")
            dev.eval("api=qaOldApi;window.qaShowCount=0;window.pywebview.api.show_render_file=async()=>{qaShowCount++;return 'C:/chosen/project.mp4'};completedRenderJob='test-result';els.downloadRender.click()")
            time.sleep(.1)
            assert dev.eval("qaShowCount===1 && qaSaves.length===6"), "Result button created another copy"
            dev.eval("els.renderDialog.close();resetRenderModal()")
            out = Path("qa_out/editor-0.4.5.png")
            out.parent.mkdir(exist_ok=True)
            dev.shot("body").save(out)
            print("PASS: editor controls, save/load, five export formats, mandatory folder, 150 Mbps control, double-click guard, result without duplicate, no JS errors")
        finally:
            if dev:
                dev.close()
            browser.terminate()
            browser.wait(timeout=10)


if __name__ == "__main__":
    main()
