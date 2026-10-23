# External MCP runtime — Lúmen

## Goal

Use maintained external MCP servers for desktop automation where they are better than reimplementing UI Automation/OCR/input. Lúmen remains responsible for intent, planning, permission checks, policy, scope, checkpoints, audit, and verification. An MCP transport is not an authorization system.

## Current implementation in this branch

- `app/mcp_runtime/stdio.py` implements a small asynchronous MCP stdio transport: subprocess start without a shell, initialize handshake, `tools/list`, and allow-listed `tools/call`.
- The server command/arguments must come from operator configuration, never from model output.
- Calls fail closed unless the exact tool name is in `allowed_tools` and was advertised by the server.
- This module is a transport primitive, not yet a claim that the full UI's ToolsController has wired every tool into the production execution path.
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
