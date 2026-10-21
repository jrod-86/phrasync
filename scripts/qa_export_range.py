"""Render a nonzero timeline interval with both 3D and flat text, locally only."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from karaokesesh.renderer import render_project
from karaokesesh.media import probe_duration, decode_test

root=Path("qa_out/export-range")
root.mkdir(parents=True,exist_ok=True)
for text_space in ["flat","scene"]:
    project={"duration":12,"timelineDuration":12,"exportRange":{"in":5,"out":5.5},
             "__renderOrigin":"http://127.0.0.1:5514",
             "canvas":{"width":320,"height":320,"fps":24},
             "background":{"type":"dynamic","visual":"scene3d","sceneKit":"ocean","textSpace":text_space},
             "style":{"fontPreset":"modern","preset":"spiral-flight","fontSize":40},
             "cues":[{"id":"a","start":5,"end":5.5,"text":"OCEAN RANGE"}],
             "export":{"preset":"ultrafast"}}
    output=root/f"range-{text_space}.mp4"
    result=render_project(project,output)
    assert result["frames"]==12 and result["duration"]==.5
    assert abs(probe_duration(output)-.5)<.08
    assert decode_test(output)[0]
    print(f"PASS actual 3D ocean / {text_space} lyrics: {result}",flush=True)
