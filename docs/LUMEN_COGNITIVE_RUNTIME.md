# Lumen Cognitive Runtime — behavioral reproduction

F35 adds the execution layer that makes the unified brain behave as a
persistent closed-loop agent.

## Reproduced capabilities

The runtime now has explicit contracts for:

- provider reasoning;
- structured context injection;
- deterministic action selection;
- governed tool execution;
- observation/evidence feedback;
- experience learning;
- bounded recovery;
- persistent continuation;
- provider/tool separation.

The provider can propose strategy and reason over the accumulated context, but
it cannot directly execute an arbitrary action. The deterministic brain remains
the authority for action selection and existing governance remains the
authority for promotion.

## Runtime

```text
goal
 -> context
 -> provider reasoning
 -> deterministic decision
 -> governed tool
 -> observation/result
 -> memory
 -> recovery or learning
 -> next decision
```

This is the architectural reproduction target: reproduce useful agent behavior,
not proprietary model weights or hidden implementation.

## Next integration boundary

The local Unreal/MCP mission runtime should instantiate one
`OperationalBrain` and drive it through `CognitiveRuntime`. Its existing
broker remains responsible for actual MCP/tool execution.

Once connected, the local provider becomes the reasoning substrate inside the
persistent cognitive loop rather than a separate chatbot.
