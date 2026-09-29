from app.computer.models import ComputerObservation, ExecutionMechanism
from app.computer_control.api import CCTarget, ScreenRegion
from app.computer_control.grounding import GroundingSource
from app.computer.targeting import TargetingEngine
from app.unreal.slate import SlateGroundingAdapter


def test_slate_text_snapshot_becomes_grounded_target():
    result = {
        "content": [{
            "type": "text",
            "text": 'button "Gaveta de Conteúdo" [ref=b16] pos=(123, 456) size=(240, 32)'
        }]
    }
    window = CCTarget(window_title_pattern="AgeOfAether", window_handle=42)
    targets = SlateGroundingAdapter().targets_from_snapshot(result, window=window)
    assert len(targets) == 1
    target = targets[0]
    assert target.label == "Gaveta de Conteúdo"
    assert target.source is GroundingSource.SLATE
    assert target.center() == (243, 472)
    assert target.window == window
    assert target.evidence == "slate_ref=b16"


def test_slate_structured_snapshot_becomes_grounded_target():
    result = {"returnValue": [{"ref": "b16", "label": "Content", "bounds": {"x": 10, "y": 20, "width": 100, "height": 30}}]}
    target = SlateGroundingAdapter().targets_from_snapshot(result)[0]
    assert target.source is GroundingSource.SLATE
    assert target.center() == (60, 35)


def test_slate_target_resolves_through_computer_control():
    target = SlateGroundingAdapter().targets_from_snapshot({
        "content": [{"type": "text", "text": 'button "Play" [ref=b9] pos=(100, 200) size=(80, 30)'}]
    })[0]
    observation = ComputerObservation(
        width=800,
        height=600,
        elements=(target,),
        active_window=CCTarget(window_title_pattern="Unreal Editor"),
        allowed_region=ScreenRegion(0, 0, 800, 600),
    )
    resolution = TargetingEngine().resolve(observation, "Play")
    assert resolution.target is target
    assert resolution.mechanism is ExecutionMechanism.COMPUTER_CONTROL

def test_slate_real_mcp_geometry_without_parentheses_and_virtual_desktop_origin():
    result = {
        "content": [{
            "type": "text",
            "text": '{"returnValue":"button \"Gaveta de Conteúdo\" [pos=-1917,1047 size=151,28] [ref=b16]"}'
        }]
    }
    targets = SlateGroundingAdapter().targets_from_snapshot(result)
    assert len(targets) == 1
    target = targets[0]
    assert target.label == "Gaveta de Conteúdo"
    assert target.source is GroundingSource.SLATE
    assert target.x == 3
    assert target.y == 1047
    assert target.width == 151
    assert target.height == 28
    assert target.evidence == "slate_ref=b16"
