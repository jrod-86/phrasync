from types import SimpleNamespace
import numpy as np
from karaokesesh.transcription_guard import gauntlet_report, pathological_repetition, whisper_options
from karaokesesh.transcribe import _decode_pass


def segment(text,start=0,end=4):
    return SimpleNamespace(text=text,start=start,end=end,words=[],compression_ratio=30,avg_logprob=-.1,temperature=1,no_speech_prob=.1)


def test_only_extreme_impossible_density_triggers_recovery():
    assert pathological_repetition(segment("do "*223))
    assert not pathological_repetition(segment("la "*50,end=20))
    assert not pathological_repetition(segment("word "*8))


def test_unrecoverable_loop_cannot_push_later_lyrics_out_of_time():
    class Model:
        def __init__(self): self.calls=[]
        def transcribe(self,source,**options):
            self.calls.append(options)
            if len(self.calls)==1:
                return iter([segment("do "*223),segment("real lyric",start=5,end=7)]),SimpleNamespace(language="pt")
            return iter([]),SimpleNamespace(language="pt")
    model=Model()
    result=_decode_pass(model,np.zeros(16000*8,dtype=np.float32),whisper_options("pt",False),offset=60,language="pt")
    assert len(model.calls)==2 and not model.calls[1]["condition_on_previous_text"]
    assert model.calls[1]["language"]=="pt"
    assert result["segments"][0]["text"]=="real lyric" and result["segments"][0]["start"]==65
    assert result["diagnostics"][0]["start"]==60
    assert result["diagnostics"][0]["loopRecovery"]=="unresolved"
    assert "60.0s" in gauntlet_report(result["diagnostics"],0,"auto")["warnings"][-1]


def test_recovered_words_stay_inside_original_window():
    class Model:
        def __init__(self): self.calls=0
        def transcribe(self,source,**options):
            self.calls+=1
            if self.calls==1:
                return iter([segment("do "*223)]),SimpleNamespace(language="pt")
            recovered=segment("real lyric",start=1,end=4.2)
            recovered.compression_ratio=1
            recovered.temperature=0
            recovered.words=[SimpleNamespace(word="real",start=1,end=2),SimpleNamespace(word="lyric",start=2,end=4.2)]
            return iter([recovered]),SimpleNamespace(language="pt")
    result=_decode_pass(Model(),np.zeros(16000*8,dtype=np.float32),whisper_options("pt",False),offset=60,language="pt")
    assert result["segments"][0]["text"]=="real lyric"
    assert result["segments"][0]["end"]==64
    assert result["segments"][0]["words"][-1]["end"]==64
    assert result["diagnostics"][0]["loopRecovery"]=="recovered"
    assert not result["diagnostics"][0]["unstable"]
