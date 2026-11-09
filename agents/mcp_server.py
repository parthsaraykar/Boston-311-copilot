"""The tool registry as an MCP server, so the same tools plug into Claude Desktop or any MCP client.

Run: python -m agents.mcp_server   (stdio)
"""
from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from agents import tools

mcp = FastMCP("boston-311-copilot")


def _register(name: str):
    fn, schema = tools.REGISTRY[name]
    desc = schema["function"]["description"]

    def wrapper(**kwargs) -> str:
        return json.dumps(tools.call(name, kwargs), default=str)

    wrapper.__name__ = name
    wrapper.__doc__ = desc
    # keep the real signature so MCP advertises typed parameters
    import inspect
    wrapper.__signature__ = inspect.signature(fn)
    wrapper.__annotations__ = {**getattr(fn, "__annotations__", {}), "return": str}
    mcp.tool(name=name, description=desc)(wrapper)


for _name in tools.REGISTRY:
    if _name != "file_request":  # filing from outside the app is not allowed
        _register(_name)

if __name__ == "__main__":
    mcp.run()
