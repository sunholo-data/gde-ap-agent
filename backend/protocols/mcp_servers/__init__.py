"""Simulated MCP servers for the AP demo (WORKFLOW-PIPELINE M3).

Mounted alongside the main /mcp server. Each one is a FastMCP instance
exposing a small set of tools that the ap-validator and ap-poster
specialists call as grounded MCP tools rather than ad-hoc Python functions.

Trust boundary: same Cloud Run service, same FastAPI process — no new
egress. The "simulation" is that the lookup_vendor / check_duplicate /
post_to_ledger / route_to_approval tools return synthetic data instead
of hitting a real vendor master or ERP. The MCP protocol path itself is
real: clients see them as proper MCP servers, the validator calls them
via the existing tools/mcp/registry McpToolset, and Cloud Trace records
them as MCP tool spans.

This is what makes the protocol claim in the design doc demonstrable —
the demo runs MCP, not "uses MCP keywords".
"""

from __future__ import annotations
