from app.computer_control.api import CCTarget
from app.unreal.integration import UnrealIntegration
from app.unreal.mcp import MCPResponse


class FakeSlateMCP:
    def __init__(self):
        self.calls = []

    def call_toolset_tool(self, toolset_name, tool_name, arguments=None):
        self.calls.append((toolset_name, tool_name, arguments))
        if tool_name == "Observe":
            return MCPResponse(result={"content": [{"type": "text", "text": "observer_1"}]})
        return MCPResponse(result={
            "content": [{
                "type": "text",
                "text": 'button "Gaveta de Conteúdo" [ref=b16] pos=(10, 20) size=(120, 30)'
            }]
        })


def test_mcp_observe_is_read_only_and_uses_slate_toolset():
    mcp = FakeSlateMCP()
    response = UnrealIntegration(mcp=mcp).mcp_observe(ref="w1", max_depth=30)
    assert not response.is_error
    assert mcp.calls == [(
        "SlateInspectorToolset.SlateInspectorToolset",
        "Observe",
        {"ref": "w1", "maxDepth": 30},
    )]


def test_mcp_slate_observation_builds_shared_computer_observation():
    mcp = FakeSlateMCP()
    window = CCTarget(window_title_pattern="AgeOfAether", window_handle=7)
    observation = UnrealIntegration(mcp=mcp).mcp_slate_observation(
        ref="w1", max_depth=30, width=800, height=600, window=window,
    )
    assert observation.width == 800
    assert observation.height == 600
    assert observation.active_window == window
    assert observation.elements[0].label == "Gaveta de Conteúdo"
    assert observation.elements[0].source.value == "slate"


def test_slate_click_planning_stops_at_computer_control_request():
    mcp = FakeSlateMCP()
    window = CCTarget(window_title_pattern="AgeOfAether", window_handle=7)
    request = UnrealIntegration(mcp=mcp).plan_slate_click(
        label="Gaveta de Conteúdo",
        ref="w1",
        max_depth=30,
        width=800,
        height=600,
        window=window,
    )
    assert request.action.value == "mouse_click"
    assert request.target is not None
    assert request.target.source.value == "slate"
    assert request.target.center() == (70, 35)
    assert all(call[1] != "Click" for call in mcp.calls)
