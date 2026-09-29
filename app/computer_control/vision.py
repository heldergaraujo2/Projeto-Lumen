from __future__ import annotations

import base64
import json
import mimetypes
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class VisionRequest:
    image_path: Path
    prompt: str
    max_output_tokens: int = 512
    max_image_bytes: int = 12 * 1024 * 1024

    def validate(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt must be non-empty")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be > 0")
        if self.max_image_bytes <= 0:
            raise ValueError("max_image_bytes must be > 0")
        if not self.image_path.is_file():
            raise FileNotFoundError(self.image_path)
        if self.image_path.stat().st_size > self.max_image_bytes:
            raise ValueError("image exceeds max_image_bytes")


@dataclass(frozen=True)
class VisionElement:
    label: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    text: str | None = None
    role: str | None = None

    def validate(self) -> None:
        if not self.label.strip():
            raise ValueError("vision element label must be non-empty")
        if not 0 <= self.confidence <= 1:
            raise ValueError("vision element confidence must be between 0 and 1")
        if min(self.x, self.y) < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("invalid vision element bounds")
        if self.text is not None and not isinstance(self.text, str):
            raise ValueError("vision element text must be a string")
        if self.role is not None and not isinstance(self.role, str):
            raise ValueError("vision element role must be a string")


@dataclass(frozen=True)
class VisionObservation:
    provider: str
    model: str
    width: int
    height: int
    elements: tuple[VisionElement, ...] = ()
    raw_text: str | None = None

    def validate(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("provider and model must be non-empty")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("invalid observation dimensions")
        if len(self.elements) > 4096:
            raise ValueError("too many vision elements")
        for element in self.elements:
            element.validate()
            if element.x + element.width > self.width or element.y + element.height > self.height:
                raise ValueError("vision element outside image")
        if self.raw_text is not None and not isinstance(self.raw_text, str):
            raise ValueError("raw_text must be a string")


class VisionProvider(Protocol):
    name: str
    model: str

    def observe(self, request: VisionRequest) -> VisionObservation:
        ...


def _repair_truncated_json(payload: str) -> dict | list | None:
    """Repair only missing closing JSON delimiters at the end of a complete value.

    This never invents fields, values, commas, or string content. If the payload
    ends inside a string or is otherwise structurally incomplete, it is rejected.
    """
    text = payload.strip()
    if not text or text[0] not in "{[":
        return None

    stack: list[str] = []
    in_string = False
    escaped = False

    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]":
            if not stack or stack[-1] != char:
                return None
            stack.pop()

    if in_string or escaped:
        return None
    if not stack:
        return None

    candidate = text + "".join(reversed(stack))
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, (dict, list)) else None


class JsonVisionProvider:
    def __init__(self, *, name: str, model: str):
        if not name.strip() or not model.strip():
            raise ValueError("provider name and model must be non-empty")
        self.name = name
        self.model = model

    def parse(self, payload: str | dict, *, width: int, height: int) -> VisionObservation:
        if isinstance(payload, str):
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as exc:
                data = _repair_truncated_json(payload)
                if data is None:
                    raise ValueError("vision provider returned invalid JSON") from exc
        else:
            data = payload
        if not isinstance(data, dict):
            raise ValueError("vision payload must be an object")
        elements = data.get("elements", [])
        if not isinstance(elements, list):
            raise ValueError("vision elements must be a list")
        items: list[VisionElement] = []
        for index, item in enumerate(elements):
            if not isinstance(item, dict):
                raise ValueError(f"vision element {index} must be an object")
            required = ("label", "confidence", "x", "y", "width", "height")
            missing = [key for key in required if key not in item]
            if missing:
                raise ValueError(f"vision element {index} missing: {', '.join(missing)}")
            try:
                element = VisionElement(
                    str(item["label"]),
                    float(item["confidence"]),
                    int(item["x"]),
                    int(item["y"]),
                    int(item["width"]),
                    int(item["height"]),
                    item.get("text"),
                    item.get("role"),
                )
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"vision element {index} has invalid fields") from exc
            element.validate()
            items.append(element)
        observation = VisionObservation(
            self.name,
            self.model,
            width,
            height,
            tuple(items),
            data.get("text"),
        )
        observation.validate()
        return observation


class OllamaVisionProvider(JsonVisionProvider):
    def __init__(
        self,
        *,
        model: str = "qwen3-vl:8b",
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 2 * 1024 * 1024,
        max_image_dimension: int = 1280,
    ):
        super().__init__(name="ollama", model=model)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be > 0")
        if max_image_dimension <= 0:
            raise ValueError("max_image_dimension must be > 0")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http or https")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_image_dimension = max_image_dimension

    def observe(self, request: VisionRequest) -> VisionObservation:
        request.validate()
        try:
            from io import BytesIO

            from PIL import Image

            with Image.open(request.image_path) as image:
                width, height = image.size
                vision_width, vision_height = width, height
                if max(width, height) > self.max_image_dimension:
                    vision_image = image.copy()
                    vision_image.thumbnail(
                        (self.max_image_dimension, self.max_image_dimension),
                        Image.Resampling.LANCZOS,
                    )
                    vision_width, vision_height = vision_image.size
                    encoded = BytesIO()
                    vision_image.save(encoded, format="PNG")
                    raw_bytes = encoded.getvalue()
                    vision_image.close()
                else:
                    raw_bytes = request.image_path.read_bytes()
        except Exception as exc:
            raise ValueError("invalid or unreadable vision image") from exc

        raw = base64.b64encode(raw_bytes).decode("ascii")
        prompt = (
            request.prompt.strip()
            + "\nReturn ONLY a JSON object with keys text and elements. "
            "Each element must contain label, confidence, x, y, width, height, "
            "and optional text and role. Coordinates must be absolute pixels "
            "relative to the supplied image."
        )
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "images": [raw],
                "stream": False,
                "format": "json",
                "options": {"num_predict": request.max_output_tokens, "temperature": 0},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/api/generate",
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                payload = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"vision provider HTTP error: {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("vision provider connection failed") from exc
        if len(payload) > self.max_response_bytes:
            raise RuntimeError("vision provider response exceeds max_response_bytes")
        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("vision provider returned invalid response JSON") from exc
        if not isinstance(data, dict) or not isinstance(data.get("response"), str):
            raise RuntimeError("Ollama response missing response")
        if (vision_width, vision_height) == (width, height):
            return self.parse(
                data["response"],
                width=width,
                height=height,
            )

        payload_text = data["response"]
        try:
            observation = self.parse(
                payload_text,
                width=vision_width,
                height=vision_height,
            )
            source_width, source_height = vision_width, vision_height
        except ValueError as scaled_error:
            # Some multimodal models preserve the original screenshot coordinate
            # system after input resizing. Accept it only when every reported
            # element is valid against the known original capture dimensions.
            try:
                observation = self.parse(
                    payload_text,
                    width=width,
                    height=height,
                )
                source_width, source_height = width, height
            except ValueError:
                raise scaled_error

        if (source_width, source_height) == (width, height):
            return observation

        scale_x = width / source_width
        scale_y = height / source_height
        elements = []
        for element in observation.elements:
            x1 = round(element.x * scale_x)
            y1 = round(element.y * scale_y)
            x2 = round((element.x + element.width) * scale_x)
            y2 = round((element.y + element.height) * scale_y)
            x1 = max(0, min(width - 1, x1))
            y1 = max(0, min(height - 1, y1))
            x2 = max(x1 + 1, min(width, x2))
            y2 = max(y1 + 1, min(height, y2))
            elements.append(
                replace(
                    element,
                    x=x1,
                    y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                )
            )
        remapped = replace(
            observation,
            width=width,
            height=height,
            elements=tuple(elements),
        )
        remapped.validate()
        return remapped


class VisionProviderManager:
    """Selects independent vision providers without coupling Lumen to one model."""

    def __init__(self, providers: tuple[VisionProvider, ...] = ()):
        self._providers: dict[str, VisionProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: VisionProvider) -> None:
        if not provider.name.strip() or not provider.model.strip():
            raise ValueError("provider name and model must be non-empty")
        key = f"{provider.name}:{provider.model}"
        if key in self._providers:
            raise ValueError(f"vision provider already registered: {key}")
        self._providers[key] = provider

    def get(self, *, name: str, model: str | None = None) -> VisionProvider:
        if model is not None:
            key = f"{name}:{model}"
            try:
                return self._providers[key]
            except KeyError as exc:
                raise KeyError(f"vision provider not registered: {key}") from exc
        matches = [provider for provider in self._providers.values() if provider.name == name]
        if len(matches) != 1:
            raise KeyError(f"vision provider selection is ambiguous or unavailable: {name}")
        return matches[0]

    def observe(
        self,
        request: VisionRequest,
        *,
        name: str,
        model: str | None = None,
    ) -> VisionObservation:
        return self.get(name=name, model=model).observe(request)
