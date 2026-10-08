from app.computer_control.api import CCTarget, ScreenRegion
from app.computer_control.grounding import (
    GroundedTarget,
    GroundingEngine,
    GroundingSource,
    TargetResolver,
)
from app.computer_control.vision import VisionElement, VisionObservation
from app.computer.windows_native import NativeElement


def target(label, source, confidence, x=10, y=10, w=20, h=10, window=None):
    return GroundedTarget(label, source, confidence, x, y, w, h, window)


def test_source_priority_is_structured_first():
    candidates = [
        target("Compile", GroundingSource.VISION, 0.99),
        target("Compile", GroundingSource.UI_AUTOMATION, 0.80, x=30),
        target("Compile", GroundingSource.NATIVE, 0.95, x=50),
    ]
    resolved, tried, reason = TargetResolver().resolve(candidates, label=" compile ")
    assert resolved.source is GroundingSource.UI_AUTOMATION
    assert tried == (GroundingSource.UI_AUTOMATION,)
    assert reason == "resolved_by_ui_automation"


def test_label_matching_is_case_and_whitespace_normalized():
    engine = GroundingEngine()
    assert engine.labels_match("  CompÍle  ", "compíle")
    assert not engine.labels_match("Compile", "Play")


def test_invalid_high_priority_candidate_does_not_block_valid_vision():
    engine = GroundingEngine(min_confidence=0.8)
    ui = target("Compile", GroundingSource.UI_AUTOMATION, 0.99, x=500, y=10)
    vision = target("Compile", GroundingSource.VISION, 0.92, x=20, y=20)
    eligible = engine.eligible(
        (ui, vision),
        scope_region=ScreenRegion(0, 0, 100, 100),
        screenshot_width=800,
        screenshot_height=600,
    )
    resolved, _, _ = TargetResolver().resolve(eligible, label="Compile")
    assert resolved is vision


def test_low_confidence_candidate_is_rejected_before_priority():
    engine = GroundingEngine(min_confidence=0.9)
    weak_native = target("Compile", GroundingSource.UI_AUTOMATION, 0.89)
    strong_vision = target("Compile", GroundingSource.VISION, 0.91, x=40)
    eligible = engine.eligible(
        (weak_native, strong_vision),
        scope_region=ScreenRegion(0, 0, 100, 100),
        screenshot_width=100,
        screenshot_height=100,
    )
    assert weak_native not in eligible
    assert strong_vision in eligible


def test_expected_window_only_constrains_candidates_with_window_identity():
    engine = GroundingEngine()
    expected = CCTarget(window_handle=10)
    native_ok = target("Compile", GroundingSource.UI_AUTOMATION, 1.0, window=expected)
    native_bad = target("Compile", GroundingSource.UI_AUTOMATION, 1.0, x=40, window=CCTarget(window_handle=11))
    vision = target("Compile", GroundingSource.VISION, 0.95, x=70)
    eligible = engine.eligible(
        (native_ok, native_bad, vision),
        scope_region=ScreenRegion(0, 0, 100, 100),
        screenshot_width=100,
        screenshot_height=100,
        expected_window=expected,
    )
    assert native_ok in eligible
    assert native_bad not in eligible
    assert vision in eligible


def test_native_elements_are_adapted_without_execution():
    element = NativeElement("Compile", "button", ScreenRegion(20, 30, 40, 20))
    targets = GroundingEngine().from_native((element,))
    assert len(targets) == 1
    assert targets[0].source is GroundingSource.UI_AUTOMATION
    assert targets[0].center() == (40, 40)


def test_deduplicate_keeps_strongest_identical_candidate():
    engine = GroundingEngine()
    weak = target("Compile", GroundingSource.VISION, 0.81)
    strong = target("Compile", GroundingSource.VISION, 0.95)
    assert engine.deduplicate((weak, strong)) == (strong,)


def test_vision_conversion_is_screenshot_bound():
    observation = VisionObservation(
        "test",
        "qwen3-vl:8b",
        200,
        120,
        (VisionElement("Compile", 0.96, 20, 30, 40, 20),),
    )
    targets = GroundingEngine(min_confidence=0.9).from_vision(observation)
    assert targets[0].source is GroundingSource.VISION
    assert targets[0].center() == (40, 40)


def test_target_outside_scope_is_not_eligible():
    engine = GroundingEngine()
    candidate = target("Compile", GroundingSource.VISION, 0.99, x=80, y=80, w=30, h=30)
    assert not engine.eligible(
        (candidate,),
        scope_region=ScreenRegion(0, 0, 100, 100),
        screenshot_width=200,
        screenshot_height=200,
    )


def test_invalid_source_order_is_rejected():
    try:
        GroundingEngine(source_order=(GroundingSource.VISION,))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
