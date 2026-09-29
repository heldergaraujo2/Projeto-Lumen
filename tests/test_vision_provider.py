import base64
import json
from pathlib import Path

import pytest
from PIL import Image

from app.computer_control.vision import (
    JsonVisionProvider,
    OllamaVisionProvider,
    VisionElement,
    VisionObservation,
    VisionProviderManager,
    VisionRequest,
)


def make_image(tmp_path: Path, size=(100, 80)) -> Path:
    path = tmp_path / "screen.png"
    Image.new("RGB", size).save(path)
    return path


def test_request_validation_and_size_limit(tmp_path):
    path = make_image(tmp_path)
    VisionRequest(path, "inspect", max_output_tokens=1, max_image_bytes=10**6).validate()
    with pytest.raises(ValueError):
        VisionRequest(path, "", max_output_tokens=1).validate()
    with pytest.raises(ValueError):
        VisionRequest(path, "inspect", max_output_tokens=0).validate()


def test_json_provider_repairs_trailing_truncation_without_inventing_values():
    provider = JsonVisionProvider(name="test", model="model")
    payload = '{"elements":[{"label":"PowerShell","confidence":0.9,"x":10,"y":20,"width":30,"height":40}'
    observation = provider.parse(payload, width=100, height=100)
    assert observation.elements[0].label == "PowerShell"
    assert observation.elements[0].width == 30


def test_json_provider_rejects_truncation_inside_string():
    provider = JsonVisionProvider(name="test", model="model")
    with pytest.raises(ValueError):
        provider.parse('{"elements":[{"label":"PowerShell"', width=100, height=100)


def test_json_provider_accepts_structured_payload():
    provider = JsonVisionProvider(name="qwen3-vl", model="8b")
    observation = provider.parse(
        json.dumps({
            "text": "Compile button visible",
            "elements": [{
                "label": "Compile", "confidence": 0.98,
                "x": 10, "y": 20, "width": 30, "height": 12,
                "role": "button",
            }],
        }),
        width=100,
        height=80,
    )
    assert observation.provider == "qwen3-vl"
    assert observation.elements[0].label == "Compile"


@pytest.mark.parametrize("payload", [
    '{"elements":"bad"}',
    '{"elements":[{"label":"Compile"}]}',
    '{"elements":[{"label":"Compile","confidence":2,"x":0,"y":0,"width":1,"height":1}]}',
    '{"elements":[{"label":"Compile","confidence":0.9,"x":99,"y":0,"width":2,"height":1}]}',
])
def test_json_provider_rejects_malformed_payloads(payload):
    provider = JsonVisionProvider(name="test", model="model")
    with pytest.raises(ValueError):
        provider.parse(payload, width=100, height=80)


def test_observation_limits_elements():
    elements = tuple(VisionElement(f"e{i}", 0.5, 0, 0, 1, 1) for i in range(4096))
    VisionObservation("p", "m", 100, 100, elements).validate()
    with pytest.raises(ValueError):
        VisionObservation("p", "m", 100, 100, elements + (elements[0],)).validate()


def test_manager_registers_and_selects_independent_models():
    a = JsonVisionProvider(name="ollama", model="qwen3-vl:8b")
    b = JsonVisionProvider(name="ollama", model="llava:latest")
    manager = VisionProviderManager((a, b))
    assert manager.get(name="ollama", model="qwen3-vl:8b") is a
    with pytest.raises(KeyError):
        manager.get(name="ollama")
    with pytest.raises(ValueError):
        manager.register(a)


def test_ollama_provider_builds_valid_contract(tmp_path, monkeypatch):
    path = make_image(tmp_path)
    provider = OllamaVisionProvider(timeout_seconds=1)

    class Response:
        def read(self, limit=-1):
            return json.dumps({
                "response": json.dumps({
                    "text": "ok",
                    "elements": [{
                        "label": "Compile", "confidence": 0.9,
                        "x": 1, "y": 2, "width": 10, "height": 8,
                    }],
                })
            }).encode()
        def __enter__(self): return self
        def __exit__(self, *args): return False

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda request, timeout: Response(),
    )
    result = provider.observe(VisionRequest(path, "inspect"))
    assert result.elements[0].label == "Compile"


def test_ollama_provider_connection_failure_is_normalized(tmp_path, monkeypatch):
    import urllib.error
    path = make_image(tmp_path)
    provider = OllamaVisionProvider(timeout_seconds=1)
    def fail(*args, **kwargs):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr("urllib.request.urlopen", fail)
    with pytest.raises(RuntimeError, match="connection failed"):
        provider.observe(VisionRequest(path, "inspect"))


def test_ollama_provider_rejects_oversized_response(tmp_path, monkeypatch):
    path = make_image(tmp_path)
    provider = OllamaVisionProvider(timeout_seconds=1, max_response_bytes=10)
    class Response:
        def read(self, limit=-1): return b"x" * 11
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="exceeds"):
        provider.observe(VisionRequest(path, "inspect"))
