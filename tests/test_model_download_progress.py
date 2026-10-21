import time

import pytest

from karaokesesh import model_download as download


def test_headless_hub_callbacks_keep_transfer_and_reconstruction_separate():
    cls, snapshot = download._byte_progress()
    with cls(unit="B", desc="Downloading bytes", total=1000) as transfer, cls(unit="B", desc="Reconstructing", total=1000, initial=100) as reconstruct:
        transfer.update(200)
        transfer.update(50)
        reconstruct.update(20)
        assert snapshot() == {"transfer": 250, "reconstruction": 120}
        assert transfer.n == 250
    with cls(desc="Fetching 5 files", total=5) as file_count:
        file_count.update(5)
    assert snapshot() == {"transfer": 250, "reconstruction": 120}


def test_preallocated_payload_cannot_force_download_progress_to_complete(tmp_path, monkeypatch):
    import huggingface_hub

    target = download.model_path(tmp_path, "tiny")
    cache = target / ".cache"
    cache.mkdir(parents=True)
    (cache / "model.bin.incomplete").write_bytes(b"x" * 10000)
    monkeypatch.setattr(download, "remote_model_size", lambda name: 10000)

    def fake_snapshot(repo, *, local_dir, allow_patterns, tqdm_class):
        with tqdm_class(unit="B", desc="Downloading bytes", total=10000) as bar:
            for _ in range(3):
                bar.update(1000)
                time.sleep(.55)
        (target / "config.json").write_text("{}")
        (target / "model.bin").write_bytes(b"done")
        return str(target)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot)
    events = []
    download.ensure_model("tiny", tmp_path, progress=lambda value, message, details: events.append(details))
    measured = [e["downloadedBytes"] for e in events if e["phase"] == "model-download" and e["totalBytes"]]
    assert 1000 in measured and 2000 in measured and 3000 in measured
    assert max(measured) == 3000
    assert events[-1]["phase"] == "model-load"


def test_cached_model_does_not_access_network(tmp_path, monkeypatch):
    target = download.model_path(tmp_path, "tiny")
    target.mkdir()
    (target / "config.json").write_text("{}")
    (target / "model.bin").write_bytes(b"cached")
    monkeypatch.setattr(download, "remote_model_size", lambda name: pytest.fail("cached model must not access network"))
    assert download.ensure_model("tiny", tmp_path) == target


def test_eta_seconds_are_not_inflated_by_half_a_minute():
    assert download._format_eta(12) == "about 12 sec remaining"
    assert download._format_eta(75) == "about 1 min remaining"


def test_metadata_lookup_has_immediate_and_periodic_progress(tmp_path, monkeypatch):
    import huggingface_hub

    def delayed_metadata(name):
        time.sleep(1.2)
        return 10

    def fake_snapshot(repo, *, local_dir, **kwargs):
        target = download.model_path(tmp_path, "tiny")
        (target / "config.json").write_text("{}")
        (target / "model.bin").write_bytes(b"done")
        return str(target)

    monkeypatch.setattr(download, "remote_model_size", delayed_metadata)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot)
    started = time.monotonic()
    events = []
    download.ensure_model("tiny", tmp_path, progress=lambda value, message, details: events.append((time.monotonic() - started, details)))
    checking = [elapsed for elapsed, details in events if details["phase"] == "model-download" and details["totalBytes"] is None]
    assert checking[0] < .5
    assert any(.9 < elapsed < 1.2 for elapsed in checking)


def test_byte_callbacks_work_without_gui_standard_streams(monkeypatch):
    import sys

    cls, snapshot = download._byte_progress()
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(sys, "stdout", None)
    with cls(unit="B", desc="Downloading bytes", total=1000) as bar:
        bar.update(250)
    assert snapshot()["transfer"] == 250
