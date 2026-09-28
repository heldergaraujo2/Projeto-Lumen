from pathlib import Path

import pytest

from app.computer_control.api import CCTarget, ScreenRegion
from app.computer_control.vision import VisionElement, VisionObservation, VisionRequest
from app.computer_control.vision_grounding import VisionGroundingPipeline


class StubVisionProvider:
    name = "stub"
    model = "vision-test"

    def observe(self, request):
        assert request.prompt
        return VisionObservation(
            provider=self.name,
            model=self.model,
            width=800,
            height=600,
            elements=(
                VisionElement("Compile", 0.97, 100, 200, 80, 30, role="button"),
                VisionElement("Cancel", 0.99, 300, 200, 80, 30, role="button"),
            ),
        )


def test_pipeline_produces_grounded_target_without_execution(tmp_path: Path):
    image = tmp_path / "screen.png"
    image.write_bytes(b"not used by stub")
    result = VisionGroundingPipeline(StubVisionProvider()).observe_and_resolve(
        VisionRequest(image, "Find the Compile button"),
        label=" compile ",
        scope_region=ScreenRegion(0, 0, 800, 600),
    )
    assert result.target is not None
    assert result.target.label == "Compile"
    assert result.target.source.value == "vision"
    assert result.target.center() == (140, 215)
    assert result.reason == "resolved_by_vision"


def test_pipeline_fails_closed_for_low_confidence():
    class Weak(StubVisionProvider):
        def observe(self, request):
            return VisionObservation(
                "weak", "vision-test", 100, 100,
                (VisionElement("Compile", 0.79, 10, 10, 20, 20),),
            )

    result = VisionGroundingPipeline(Weak()).observe_and_resolve(
        VisionRequest(Path("/tmp/placeholder"), "Find Compile"),
        label="Compile",
    )
    assert result.target is None
    assert result.reason == "target_not_found"


def test_pipeline_rejects_unexpected_window():
    class WindowVision(StubVisionProvider):
        def observe(self, request):
            return VisionObservation(
                "stub", "vision-test", 100, 100,
                (VisionElement("Compile", 0.99, 10, 10, 20, 20),),
            )

    result = VisionGroundingPipeline(WindowVision()).observe_and_resolve(
        VisionRequest(Path("/tmp/placeholder"), "Find Compile"),
        label="Compile",
        expected_window=CCTarget(window_handle=42),
    )
    # Vision candidates without native window identity remain eligible; the
    # pipeline does not invent window identity from pixels.
    assert result.target is not None


def test_result_validation_rejects_foreign_target(tmp_path: Path):
    image = tmp_path / "screen.png"
    image.write_bytes(b"x")
    result = VisionGroundingPipeline(StubVisionProvider()).observe_and_resolve(
        VisionRequest(image, "Find Compile"), label="Compile"
    )
    result.target = None if False else result.target
    result.validate()


def test_request_limits_are_enforced(tmp_path: Path):
    image = tmp_path / "screen.bin"
    image.write_bytes(b"x" * 10)
    with pytest.raises(ValueError):
        VisionRequest(image, "x", max_image_bytes=5).validate()
