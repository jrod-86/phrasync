from __future__ import annotations

import json
import re
import shutil
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import JOBS_DIR, RENDERS_DIR
from .diagnostics import log_event, log_exception
from .align import align_cues, alignment_stats
from .audio_analysis import analyze_audio
from .lyric_sync import apply_lyric_sync
from .qa import postflight_render, preflight_project
from .renderer import render_project
from .stems import StemsCancelled, separate_file
from .encoding import container, encoder_label, nvenc_problem, video_enabled
from .export_extras import export_audio, export_captions, reserve_path
from .storage import store_path
from .media import probe_duration
from .config import TMP_DIR
from .transcribe import TranscriptionCancelled, transcribe_audio


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_title(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return cleaned[:64] or "karaokesesh_export"


@dataclass
class Job:
    id: str
    kind: str
    state: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    result: dict[str, Any] | None = None
    error: str | None = None
    traceback: str | None = None
    preflight: dict[str, Any] | None = None
    postflight: dict[str, Any] | None = None
    request: dict[str, Any] | None = None
    cancel_requested: bool = False
    phase: str | None = None
    downloaded_bytes: int | None = None
    transferred_bytes: int | None = None
    reconstructed_bytes: int | None = None
    total_bytes: int | None = None
    eta_seconds: int | None = None
    device: str | None = None

    def public(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("traceback", None)
        return data


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="karaokesesh-job")

    def _save(self, job: Job) -> None:
        job.updated_at = _utc_now()
        (JOBS_DIR / f"{job.id}.json").write_text(
            json.dumps(job.public(), indent=2), encoding="utf-8"
        )

    def create_render(self, project: dict[str, Any], title: str = "karaokesesh_export", output_dir: Path | None = None) -> Job:
        if output_dir is None or not output_dir.is_dir():
            raise ValueError("Choose an export folder before starting a render")
        job = Job(id=uuid.uuid4().hex, kind="render")
        log_event("info", "render", f"Queued job {job.id[:8]}")
        with self.lock:
            self.jobs[job.id] = job
            self._save(job)
        self.executor.submit(self._run_render, job.id, project, title, output_dir)
        return job

    def create_transcription(
        self,
        path: Path,
        model: str,
        language: str,
        vad_filter: bool,
        align: bool = True,
        language_spans: list[dict[str, Any]] | None = None,
        lyrics: str = "",
        gpu: int | None = None,
    ) -> Job:
        job = Job(
            id=uuid.uuid4().hex,
            kind="transcription",
            message="Waiting to transcribe",
            request={
                "model": model,
                "language": language or "auto",
                "task": "transcribe",
                "vadFilter": bool(vad_filter),
                "align": bool(align),
                "languageSpans": list(language_spans or []),
                "lyrics": bool(str(lyrics or "").strip()),
                "gpu": gpu,
            },
        )
        log_event("info", "transcription", f"Queued job {job.id[:8]}, model {model}, language {language}")
        with self.lock:
            self.jobs[job.id] = job
            self._save(job)
        self.executor.submit(
            self._run_transcription,
            job.id,
            path,
            model,
            language,
            vad_filter,
            align,
            language_spans,
            lyrics,
            gpu,
        )
        return job

    def _run_transcription(
        self,
        job_id: str,
        path: Path,
        model: str,
        language: str,
        vad_filter: bool,
        align: bool,
        language_spans: list[dict[str, Any]] | None = None,
        lyrics: str = "",
        gpu: int | None = None,
    ) -> None:
        job = self.get(job_id)
        if not job:
            return

        def cancelled() -> bool:
            with self.lock:
                return job.cancel_requested

        def update(value: float, message: str, details: dict[str, Any] | None = None) -> None:
            with self.lock:
                job.progress = max(job.progress, min(0.84, 0.04 + float(value) * 0.80))
                job.message = message
                if details:
                    if "phase" in details:
                        job.phase = details["phase"]
                    if "downloadedBytes" in details:
                        job.downloaded_bytes = details["downloadedBytes"]
                    if "transferredBytes" in details:
                        job.transferred_bytes = details["transferredBytes"]
                    if "reconstructedBytes" in details:
                        job.reconstructed_bytes = details["reconstructedBytes"]
                    if "totalBytes" in details:
                        job.total_bytes = details["totalBytes"]
                    if "etaSeconds" in details:
                        job.eta_seconds = details["etaSeconds"]
                    if "device" in details:
                        job.device = details["device"]
                elif job.phase in {"model-download", "model-load"}:
                    job.phase = "transcribing"
                    job.eta_seconds = None
                self._save(job)

        try:
            if cancelled():
                raise TranscriptionCancelled("Transcription cancelled")
            with self.lock:
                job.state = "running"
                job.progress = 0.02
                job.message = f"Loading Whisper {model}"
                self._save(job)

            result = transcribe_audio(
                path,
                model,
                language,
                vad_filter,
                progress=update,
                cancel_check=cancelled,
                language_spans=language_spans,
                **({"gpu": gpu} if gpu is not None else {}),
            )
            if cancelled():
                raise TranscriptionCancelled("Transcription cancelled")

            if str(lyrics or "").strip():
                with self.lock:
                    job.message = "Matching your lyrics to the song"
                    job.phase = "lyric-sync"
                    self._save(job)
                apply_lyric_sync(result, lyrics)

            if align:
                with self.lock:
                    job.progress = 0.88
                    job.message = "Analysing audio for alignment"
                    job.phase = "aligning"
                    self._save(job)
                analysis = analyze_audio(path, True)
                if cancelled():
                    raise TranscriptionCancelled("Transcription cancelled")
                aligned = align_cues(result["cues"], analysis)
                result["cues"] = aligned["cues"]
                result["alignment"] = aligned["report"]
                result["alignmentStats"] = alignment_stats(aligned["cues"], analysis)

            with self.lock:
                job.result = result
                job.state = "complete"
                job.progress = 1.0
                job.message = "Transcription complete"
                job.phase = "complete"
                self._save(job)
            log_event("info", "transcription", f"Completed job {job.id[:8]} on {job.device or 'unknown device'}")
        except TranscriptionCancelled:
            with self.lock:
                job.state = "cancelled"
                job.message = "Transcription cancelled"
                job.error = None
                self._save(job)
        except Exception as exc:
            log_exception("transcription", exc)
            with self.lock:
                job.state = "cancelled" if job.cancel_requested else "failed"
                job.error = None if job.cancel_requested else str(exc)
                job.traceback = traceback.format_exc()
                job.message = "Transcription cancelled" if job.cancel_requested else "Transcription failed"
                self._save(job)

    def create_stems(self, path: Path, name: str, gpu: int | None = None) -> Job:
        job = Job(id=uuid.uuid4().hex, kind="stems", message="Waiting to remove vocals",
                  request={"gpu": gpu})
        log_event("info", "stems", f"Queued job {job.id[:8]}")
        with self.lock:
            self.jobs[job.id] = job
            self._save(job)
        self.executor.submit(self._run_stems, job.id, path, name, gpu)
        return job

    def _run_stems(self, job_id: str, path: Path, name: str, gpu: int | None) -> None:
        job = self.get(job_id)
        if not job:
            return

        def cancelled() -> bool:
            with self.lock:
                return job.cancel_requested

        def update(value: float, message: str) -> None:
            with self.lock:
                job.progress = max(job.progress, min(0.97, float(value)))
                job.message = message
                self._save(job)

        work = TMP_DIR / f"stems-{job_id}"
        try:
            with self.lock:
                job.state = "running"
                job.message = "Preparing the vocal remover"
                self._save(job)
            outputs = separate_file(path, work, gpu, update, cancelled)
            result: dict[str, Any] = {}
            stem = Path(name).stem or "song"
            for key, label in (("instrumental", "Instrumental"), ("vocals", "Vocals")):
                asset = store_path("audio", outputs[key], f"{stem} - {label}.wav")
                public = asset.public()
                public["duration"] = probe_duration(Path(asset.path))
                result[key] = public
            with self.lock:
                job.result = result
                job.state = "complete"
                job.progress = 1.0
                job.message = "Vocals removed"
                self._save(job)
            log_event("info", "stems", f"Completed job {job.id[:8]}")
        except StemsCancelled:
            with self.lock:
                job.state = "cancelled"
                job.message = "Vocal removal cancelled"
                self._save(job)
        except Exception as exc:
            log_exception("stems", exc)
            with self.lock:
                job.state = "cancelled" if job.cancel_requested else "failed"
                job.error = None if job.cancel_requested else str(exc)
                job.traceback = traceback.format_exc()
                job.message = "Vocal removal cancelled" if job.cancel_requested else "Vocal removal failed"
                self._save(job)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _run_render(self, job_id: str, project: dict[str, Any], title: str, output_dir: Path) -> None:
        job = self.get(job_id)
        if not job:
            return
        output_path = None
        settings = project.get("export") or {}
        want_video = video_enabled(project)
        audio_format = str((settings.get("audio") or {}).get("format") or "") if (settings.get("audio") or {}).get("enabled") else ""
        caption_format = str((settings.get("captions") or {}).get("format") or "") if (settings.get("captions") or {}).get("enabled") else ""
        try:
            if not (want_video or audio_format or caption_format):
                raise ValueError("Turn on video, audio or captions to export something.")
            if want_video:
                report = preflight_project(project)
                with self.lock:
                    job.preflight = report.public()
                    if not report.ok:
                        job.state = "failed"
                        job.error = "Preflight critic found blocking errors."
                        job.progress = 1.0
                        job.message = "Preflight failed"
                        self._save(job)
                        log_event("error", "render", f"Job {job.id[:8]} failed preflight")
                        return
            with self.lock:
                job.state = "running"
                job.progress = 0.01
                job.message = "Starting renderer" if want_video else "Exporting"
                self._save(job)

            base = _safe_title(title)

            def update(value: float, message: str) -> None:
                with self.lock:
                    job.progress = max(job.progress, min(1.0, float(value)))
                    job.message = message
                    self._save(job)

            def cancelled() -> bool:
                with self.lock:
                    return job.cancel_requested

            result: dict[str, Any] = {}
            postflight = None
            if want_video:
                output_path = reserve_path(output_dir, base, container(project))
                encoder_note = encoder_label(project)
                problem = nvenc_problem(project)
                if problem:
                    # No NVENC in this FFmpeg or driver: still deliver the video.
                    log_event("warning", "render", f"NVIDIA encoding unavailable, using CPU: {problem}")
                    project = {**project, "export": {**(project.get("export") or {}), "encoder": "cpu"}}
                    encoder_note = "CPU (NVIDIA encoding unavailable)"
                result = render_project(project, output_path, progress=update, cancel_check=cancelled)
                result["encoder"] = encoder_note
                postflight = postflight_render(output_path, expected_duration=result.get("duration"))
                result["filename"] = output_path.name
                result["downloadUrl"] = f"/api/render/{job.id}/download"
            files = [result["path"]] if want_video else []
            if audio_format and (postflight is None or postflight.ok):
                update(job.progress, "Exporting audio")
                files.append(str(export_audio(project, output_dir, base, audio_format)))
            if caption_format and (postflight is None or postflight.ok):
                files.append(str(export_captions(project, output_dir, base, caption_format)))
            result["files"] = files
            if not want_video:
                result["path"] = files[0]
                result["filename"] = Path(files[0]).name
            with self.lock:
                job.result = result
                job.postflight = postflight.public() if postflight else None
                job.progress = 1.0
                if postflight is None or postflight.ok:
                    job.state = "complete"
                    job.message = "Export complete"
                else:
                    job.state = "failed"
                    job.error = "Post-render critic found a blocking error."
                    job.message = "Postflight failed"
                self._save(job)
            ok = postflight is None or postflight.ok
            log_event("info" if ok else "error", "render", f"Job {job.id[:8]} {'complete' if ok else 'failed postflight'}")
        except Exception as exc:
            if output_path is not None and output_path.exists() and output_path.stat().st_size == 0:
                output_path.unlink()
            log_exception("render", exc)
            with self.lock:
                job.state = "cancelled" if job.cancel_requested else "failed"
                job.error = str(exc)
                job.traceback = traceback.format_exc()
                job.progress = 1.0
                job.message = "Cancelled" if job.cancel_requested else "Render failed"
                self._save(job)

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.state not in {"queued", "running"}:
                return False
            job.cancel_requested = True
            job.message = "Cancellation requested"
            self._save(job)
            return True

    def output_path(self, job_id: str) -> Path | None:
        job = self.get(job_id)
        if not job or not job.result:
            return None
        path = Path(job.result.get("path", ""))
        return path if path.exists() else None


manager = JobManager()
