import threading
import time
from pathlib import Path

import karaokesesh.jobs as jobs_module
from karaokesesh.jobs import JobManager
from karaokesesh.transcribe import TranscriptionCancelled


def test_transcription_job_reports_progress_and_cancels(monkeypatch):
    manager = JobManager()
    monkeypatch.setattr(manager, "_save", lambda job: None)
    started = threading.Event()

    def fake_transcribe(path, model, language, vad_filter, *, progress, cancel_check, language_spans=None):
        started.set()
        progress(0.4, "Transcribed 4.0s of 10.0s")
        while not cancel_check():
            time.sleep(0.005)
        raise TranscriptionCancelled("Transcription cancelled")

    monkeypatch.setattr(jobs_module, "transcribe_audio", fake_transcribe)
    job = manager.create_transcription(Path("song.wav"), "base", "auto", False, False)
    assert started.wait(timeout=1)
    assert manager.get(job.id).progress > 0
    assert manager.cancel(job.id) is True

    deadline = time.monotonic() + 1
    while manager.get(job.id).state != "cancelled" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert manager.get(job.id).state == "cancelled"
    manager.executor.shutdown(wait=True)
