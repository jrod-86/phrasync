import pytest

from karaokesesh.loudness import DEFAULT_TARGET, loudness_filter, measure, normalize_target
from karaokesesh.media import run_ffmpeg


def song(path, volume_db):
    run_ffmpeg(["-hide_banner", "-y", "-f", "lavfi", "-i", "anoisesrc=color=pink:sample_rate=48000:duration=6:seed=3",
                "-af", f"volume={volume_db}dB", "-ac", "2", "-c:a", "pcm_s32le", str(path)])


def apply(source, chain, output):
    run_ffmpeg(["-hide_banner", "-y", "-i", str(source), "-af", chain, "-c:a", "pcm_s16le", str(output)])


def test_target_defaults_on_and_respects_the_tick_box():
    assert normalize_target({}) == DEFAULT_TARGET == -14
    assert normalize_target({"export": {"normalize": {"enabled": True, "target": -16}}}) == -16
    assert normalize_target({"export": {"normalize": {"enabled": False}}}) is None
    assert normalize_target({"export": {"normalize": {"target": -3}}}) == -14


@pytest.mark.parametrize("target", [-14, -16])
def test_quiet_and_loud_songs_land_on_the_target(tmp_path, target):
    project = {"export": {"normalize": {"enabled": True, "target": target}}}
    for volume in (-25, -2):
        source, output = tmp_path / f"in{volume}.wav", tmp_path / f"out{volume}.wav"
        song(source, volume)
        chain = loudness_filter(project, source, 0.0, None)
        assert "linear=true" in chain and "aresample=48000" in chain
        apply(source, chain, output)
        result = measure(output, 0.0, None, target)
        assert result["input_i"] == pytest.approx(target, abs=1.0)
        assert result["input_tp"] <= -0.5


def test_unticked_or_silent_means_no_filter(tmp_path):
    source = tmp_path / "song.wav"
    song(source, -10)
    assert loudness_filter({"export": {"normalize": {"enabled": False}}}, source, 0.0, None) is None
    silent = tmp_path / "silent.wav"
    run_ffmpeg(["-hide_banner", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "2", str(silent)])
    assert loudness_filter({}, silent, 0.0, None) is None
