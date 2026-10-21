"""Read-only comparison of a pathological decode window; never edits a project."""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karaokesesh.transcribe import _load_model, _device_config, MODEL_DIR, _decode_pass, transcribe_audio
from karaokesesh.language_map import load_audio
from karaokesesh.transcription_guard import whisper_options

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: diagnose_song_loop.py AUDIO_FILE")
    source = Path(sys.argv[1])
    audio = load_audio(source)
    device, compute = _device_config()
    model = _load_model(str(MODEL_DIR / "large-v3"), device, compute)
    for start, end in [(58.63,80.38),(75.5,81.0)]:
        options = whisper_options("auto", False)
        options["condition_on_previous_text"] = False
        outcome = _decode_pass(model,audio[round(start*16000):round(end*16000)],options,offset=start)
        print(json.dumps({"window":[start,end],"language":outcome["info"].language,"segments":outcome["segments"],"diagnostics":outcome["diagnostics"]},ensure_ascii=False),flush=True)
    result=transcribe_audio(source,"large-v3","auto",False)
    print(json.dumps({"fullTrack":True,"model":result["model"],"device":result["device"],"diagnostics":result["segmentDiagnostics"],
        "middleCues":[{key:cue.get(key) for key in ["start","end","text","language"]} for cue in result["cues"] if 55<cue["start"]<100]},ensure_ascii=False),flush=True)
