"""Independent read-only ASR comparison for the saved song's opening."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from karaokesesh.transcribe import _device_config, _load_model

device, compute = _device_config()
model = _load_model('C:/Users/w4k3/.karaokesesh/models/large-v3', device, compute)
segments, info = model.transcribe('qa_out/timing-original-song.wav', language='en',
    word_timestamps=True, vad_filter=False, condition_on_previous_text=False, beam_size=5)
result = {'device': device, 'offset': 11.8, 'words': [
    {'text': w.word, 'start': round(w.start + 11.8, 4), 'end': round(w.end + 11.8, 4)}
    for s in segments for w in (s.words or [])]}
Path('qa_out/timing-song-asr-crosscheck.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
