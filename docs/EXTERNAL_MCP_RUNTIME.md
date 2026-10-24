# External MCP runtime — Lúmen

## Goal

Use maintained external MCP servers for desktop automation where they are better than reimplementing UI Automation/OCR/input. Lúmen remains responsible for intent, planning, permission checks, policy, scope, checkpoints, audit, and verification. An MCP transport is not an authorization system.

## Current implementation in this branch

- `app/mcp_runtime/stdio.py` implements a small asynchronous MCP stdio transport: subprocess start without a shell, initialize handshake, `tools/list`, and allow-listed `tools/call`.
- The server command/arguments must come from operator configuration, never from model output.
- Calls fail closed unless the exact tool name is in `allowed_tools` and was advertised by the server.
- MCPCallTool is registered through the existing ToolsController and ToolRegistry when data/mcp_servers.json enables a server and allow-lists at least one tool. The planner exposes only the generic mcp_call entry, not arbitrary discovered tools.
- mcp_call requires the existing COMPUTER_CONTROL permission and a mandatory explicit checkpoint before dispatch. Calls verify that the server is enabled and the exact tool is allow-listed and advertised by the server.
- The explicit checkpoint remains mandatory even when global autonomous mode is enabled; autonomous mode does not silently approve calls into external processes.
- Child processes inherit only a small allow-list of operating-system environment variables. Application/API secrets are not inherited unless the operator explicitly places a value in that server's `env` configuration.
- The production path is wired in code, but no server is enabled by default and no real UI action has yet been proven on the user's PC.
- `config/mcp_servers.example.json` is an example only. It is deliberately disabled with an empty allow-list. Review the current upstream README/package command before enabling it; package names and launch arguments can change.

## Candidate desktop server

Initial candidate: [desk-mcp](https://github.com/DigitalDog1/desk-mcp). It advertises Windows UI Automation/MSAA, OCR, browser DOM/CDP, mouse/keyboard, window management, and verification. Validate the exact npm package and launch command against the upstream README before enabling. Do not expose all advertised tools by default.

Keep the existing Unreal MCP client for Unreal-specific Slate/editor operations. Do not replace or re-run the completed F30 validation merely because a general desktop MCP is added.

## Required integration sequence

1. Add a configuration loader with schema validation and environment expansion restricted to named variables.
2. Register the MCP client through the existing ToolsController/ToolRegistry path; map tool schema and results into the existing ToolProtocol.
3. Require existing Lúmen permission and policy checks before each tool call; high-impact tools require a checkpoint/human approval.
4. Store only sanitized metadata in audit logs; do not log screenshot bytes, prompt contents, credentials, or arbitrary tool output.
5. Verify postconditions from a fresh observation; an MCP response alone is not proof of UI state change.
6. Add mocked protocol tests and Windows-only smoke tests using a harmless UI action, then run through the actual Lúmen UI.
7. Pin package versions and document licenses, update cadence, and rollback before enabling on the user's PC.

## Security / operational rules

- Never use shell command strings; launch with an argument array.
- Do not enable all tools automatically.
- Keep desktop access opt-in until the local UI smoke tests pass.
- Destructive file, registry, process, credential, install/uninstall, shutdown/restart actions must be separately permissioned and checkpointed.
- A server timeout, invalid JSON-RPC message, or unknown tool is a failure, not a success.
- MCP server stdout is protocol-only; stderr is suppressed by this initial client to avoid blocking on a full pipe. Add a bounded sanitized diagnostic channel before production use.

## What remains unproven

This code has not been run on the user's Windows PC from this environment. It does not prove that an external server is installed, that its command works, or that the production UI exposes the tools. Those require local Windows tests and UI verification.


## Local configuration

The UI controller reads data/mcp_servers.json. The tracked config/mcp_servers.example.json is only a template and deliberately has no allow-listed tools. Copy it to the runtime data directory, then set the actual executable/argument array and the reviewed tool names using the selected server's current official documentation. Do not enable a server with a guessed command or blindly allow-list every tool. A missing file means no external MCP capability is exposed.

Example conceptual shape (replace placeholders with verified local values):

    {
      "schema_version": 1,
      "servers": [{
        "name": "desktop-ui",
        "transport": "stdio",
        "command": "<verified executable path>",
        "args": ["<verified argument>"],
        "cwd": null,
        "env": {},
        "enabled": true,
        "allowed_tools": ["<reviewed tool name>"],
        "request_timeout_seconds": 30,
        "startup_timeout_seconds": 15
      }]
    }

The current adapter launches and shuts down the server per tool call. This favors isolation and simple cleanup over latency; if the chosen MCP requires a persistent session or long-running initialization, test that behavior before changing the lifecycle.

## Verification boundary

The GitHub Actions suite validates the generic protocol against a local fake MCP process and the controller wiring. It does not install the external desktop server, grant computer-control permission, open the local Lumen UI, capture the physical screen, or test the microphone and speakers. Those are separate Windows acceptance tests.
