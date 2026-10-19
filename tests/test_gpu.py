from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import phrasync.cuda as cuda_module
import phrasync.transcribe as transcribe_module

SMI = "0, NVIDIA GeForce RTX 3090, 18000, 24576, 97\n1, NVIDIA RTX A4500, 600, 20470, 0\n"


def test_gpus_are_listed_in_nvidia_smi_order(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.setattr(cuda_module.shutil, "which", lambda name: "nvidia-smi")
    monkeypatch.setattr(cuda_module.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=SMI))
    gpus = cuda_module.list_gpus()
    assert [(gpu["index"], gpu["name"]) for gpu in gpus] == [(0, "NVIDIA GeForce RTX 3090"), (1, "NVIDIA RTX A4500")]
    assert gpus[1]["memoryUsedMb"] == 600.0
    assert cuda_module.os.environ["CUDA_DEVICE_ORDER"] == "PCI_BUS_ID"


def test_a_launcher_pin_hides_the_picker(monkeypatch):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-abc")
    assert cuda_module.list_gpus() == []


def test_chosen_gpu_falls_back_to_the_first_when_missing(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "ctranslate2", SimpleNamespace(get_cuda_device_count=lambda: 2))
    assert transcribe_module._device_index("cuda", 1) == 1
    assert transcribe_module._device_index("cuda", 5) == 0
    assert transcribe_module._device_index("cuda", None) == 0
    assert transcribe_module._device_index("cpu", 1) == 0


def test_api_lists_gpus_and_passes_the_choice_to_whisper(monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "list_gpus", lambda: [{"index": 1, "name": "NVIDIA RTX A4500"}])
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    client = TestClient(app_module.app)
    assert client.get("/api/gpus").json()["gpus"][0]["index"] == 1
    assert app_module._gpu_choice({"gpu": 1}) == 1
    assert app_module._gpu_choice({"gpu": "auto"}) is None
    assert app_module._gpu_choice({}) is None
