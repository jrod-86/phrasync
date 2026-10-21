from pathlib import Path
import pytest
from karaokesesh.renderer import _build_context, render_project
from karaokesesh.media import probe_duration, decode_test, run_ffmpeg
from karaokesesh.storage import store_path


def project():
    return {"duration":10,"canvas":{"width":320,"height":320,"fps":24},
            "background":{"type":"dynamic","visual":"aurora"},
            "style":{"fontPreset":"modern"},
            "cues":[{"id":"a","start":5,"end":6,"text":"RANGE"}],
            "exportRange":{"in":5,"out":6},"export":{"preset":"ultrafast"}}


def test_range_context_retains_absolute_lyrics_and_uses_short_duration():
    ctx=_build_context(project())
    assert ctx.start_time==5 and ctx.duration==1 and ctx.frame_count==24
    assert ctx.cues[0]["start"]==5
    assert len(ctx.envelope)==24


@pytest.mark.parametrize("selected",[{"in":6,"out":5},{"in":-1,"out":6},{"in":5,"out":11},{"in":5,"out":float("nan")}])
def test_invalid_ranges_rejected(selected):
    p=project();p["exportRange"]=selected
    with pytest.raises(ValueError):_build_context(p)


def test_manual_duration_can_shorten_or_extend_timeline():
    p=project();del p["exportRange"]
    for value in [2,20]:
        p["timelineDuration"]=value
        assert _build_context(p).duration==value


def test_real_short_range_export(tmp_path):
    output=tmp_path/"range.mp4"
    result=render_project(project(),output)
    assert result["duration"]==1 and result["frames"]==24
    assert abs(probe_duration(output)-1)<.05
    assert decode_test(output)[0]


def test_audio_is_cut_from_in_not_from_song_start(tmp_path):
    import numpy as np
    source=tmp_path/"tone.wav"
    run_ffmpeg(["-y","-f","lavfi","-i","sine=frequency=900:sample_rate=8000:duration=7",
                "-af","volume=enable='lt(t,5)':volume=0",str(source)],check=True)
    asset=store_path("audio",source)
    try:
        p=project();p["audioAssetId"]=asset.id
        output=tmp_path/"audio-range.mp4"
        render_project(p,output)
        decoded=run_ffmpeg(["-i",str(output),"-vn","-ac","1","-ar","8000","-f","f32le","pipe:1"],check=True)
        samples=np.frombuffer(decoded.stdout,dtype=np.float32)
        assert np.sqrt(np.mean(samples**2))>.03
        assert abs(probe_duration(output)-1)<.08
    finally:
        Path(asset.path).unlink(missing_ok=True)
