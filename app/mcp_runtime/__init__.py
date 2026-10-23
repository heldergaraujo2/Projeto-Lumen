"""Generic, policy-gated MCP stdio runtime for Lumen.

This package deliberately does not launch servers from arbitrary model output.
Servers must be configured by the application/operator and tool names must be
allow-listed before a call can be made.
"""
from .stdio import MCPError, MCPServerConfig, MCPStdioClient, MCPTool

__all__ = ["MCPError", "MCPServerConfig", "MCPStdioClient", "MCPTool"]
