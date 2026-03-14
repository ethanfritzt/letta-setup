"""
MCP Server Setup - Register external MCP servers with Letta.

This module programmatically registers MCP servers (GitHub, Home Assistant, Filesystem)
with the Letta server before agent creation. Each server is conditional on environment
variables - if not set, the server is skipped gracefully.

The setup is idempotent — if a server is already registered, it will be reused
rather than creating a duplicate.

Supported transports:
- stdio: For local MCP servers (GitHub, Filesystem via npx)
- streamable_http: For remote MCP servers (Home Assistant add-on)
"""

import os
from dataclasses import dataclass

from letta_client import Letta


@dataclass
class MCPServerInfo:
    """Information about a registered MCP server."""
    name: str
    server_id: str
    tool_ids: list[str]
    tool_names: list[str]
    was_created: bool = True  # False if reusing existing server


def _find_existing_mcp_server(client: Letta, server_name: str):
    """
    Find an existing MCP server by name.

    Args:
        client: Letta client instance
        server_name: Name of the MCP server to find

    Returns:
        The server object if found, None otherwise
    """
    try:
        servers = client.mcp_servers.list()
        for server in servers:
            if getattr(server, 'server_name', None) == server_name:
                return server
            # Also check 'name' attribute as fallback
            if getattr(server, 'name', None) == server_name:
                return server
    except Exception:
        pass
    return None


def _get_server_tools(client: Letta, server_id: str) -> tuple[list[str], list[str]]:
    """
    Get tool IDs and names from an MCP server.

    Args:
        client: Letta client instance
        server_id: ID of the MCP server

    Returns:
        Tuple of (tool_ids, tool_names)
    """
    # Try the newer API first (mcp_servers.tools.list)
    try:
        tools = client.mcp_servers.tools.list(server_id)
        tool_ids = [t.id for t in tools]
        tool_names = [t.name for t in tools]
        return tool_ids, tool_names
    except AttributeError:
        pass

    # Fall back to older API (mcp_servers.list_tools)
    try:
        tools = client.mcp_servers.list_tools(server_id)
        tool_ids = [t.id for t in tools]
        tool_names = [t.name for t in tools]
        return tool_ids, tool_names
    except Exception:
        return [], []


def _register_github_mcp(client: Letta) -> MCPServerInfo | None:
    """
    Find or register the GitHub MCP server (streamable_http transport).

    Uses the GitHub Copilot API endpoint (api.githubcopilot.com) which provides
    better streaming support than the stdio-based MCP server.

    Requires: GH_TOKEN environment variable (GitHub PAT).
    Falls back to GITHUB_MCP_TOKEN for backwards compatibility.
    """
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_MCP_TOKEN")
    if not token:
        print("Skipping GitHub MCP: GH_TOKEN not set")
        return None

    try:
        # Check for existing server
        existing = _find_existing_mcp_server(client, "github")
        if existing:
            tool_ids, tool_names = _get_server_tools(client, existing.id)
            print(f"Found existing GitHub MCP: {len(tool_ids)} tools")
            return MCPServerInfo(
                name="github",
                server_id=existing.id,
                tool_ids=tool_ids,
                tool_names=tool_names,
                was_created=False,
            )

        # Register new server
        server = client.mcp_servers.create(
            server_name="github",
            config={
                "mcp_server_type": "streamable_http",
                "server_url": "https://api.githubcopilot.com/mcp/",
                "auth_header": "Authorization",
                "auth_token": f"Bearer {token}",
            }
        )

        tool_ids, tool_names = _get_server_tools(client, server.id)
        print(f"Registered GitHub MCP: {len(tool_ids)} tools")
        return MCPServerInfo(
            name="github",
            server_id=server.id,
            tool_ids=tool_ids,
            tool_names=tool_names,
            was_created=True,
        )

    except Exception as e:
        print(f"Warning: Failed to register GitHub MCP: {e}")
        return None


def _register_homeassistant_mcp(client: Letta) -> MCPServerInfo | None:
    """
    Find or register the Home Assistant MCP server (streamable_http transport).

    Requires: HOMEASSISTANT_MCP_URL environment variable.
    Optional: HOMEASSISTANT_TOKEN for authentication.
    """
    mcp_url = os.getenv("HOMEASSISTANT_MCP_URL")
    if not mcp_url:
        print("Skipping Home Assistant MCP: HOMEASSISTANT_MCP_URL not set")
        return None

    token = os.getenv("HOMEASSISTANT_TOKEN", "")

    try:
        # Check for existing server
        existing = _find_existing_mcp_server(client, "home-assistant")
        if existing:
            tool_ids, tool_names = _get_server_tools(client, existing.id)
            print(f"Found existing Home Assistant MCP: {len(tool_ids)} tools")
            return MCPServerInfo(
                name="home-assistant",
                server_id=existing.id,
                tool_ids=tool_ids,
                tool_names=tool_names,
                was_created=False,
            )

        # Register new server
        config = {
            "mcp_server_type": "streamable_http",
            "server_url": mcp_url,
        }

        # Add auth if token is provided
        if token:
            config["auth_header"] = "Authorization"
            config["auth_token"] = f"Bearer {token}"

        server = client.mcp_servers.create(
            server_name="home-assistant",
            config=config
        )

        tool_ids, tool_names = _get_server_tools(client, server.id)
        print(f"Registered Home Assistant MCP: {len(tool_ids)} tools")
        return MCPServerInfo(
            name="home-assistant",
            server_id=server.id,
            tool_ids=tool_ids,
            tool_names=tool_names,
            was_created=True,
        )

    except Exception as e:
        print(f"Warning: Failed to register Home Assistant MCP: {e}")
        return None


def _register_filesystem_mcp(client: Letta) -> MCPServerInfo | None:
    """
    Find or register the Filesystem MCP server (stdio transport).

    Provides file read/write/search/list tools for the document store
    (SilverBullet data directory). Agents use these tools to create and
    read markdown documents that are viewable in the SilverBullet web UI.

    Requires: DOCUMENT_STORE_PATH environment variable.
    """
    doc_path = os.getenv("DOCUMENT_STORE_PATH")
    if not doc_path:
        print("Skipping Filesystem MCP: DOCUMENT_STORE_PATH not set")
        return None

    try:
        # Check for existing server
        existing = _find_existing_mcp_server(client, "filesystem")
        if existing:
            tool_ids, tool_names = _get_server_tools(client, existing.id)
            print(f"Found existing Filesystem MCP: {len(tool_ids)} tools")
            return MCPServerInfo(
                name="filesystem",
                server_id=existing.id,
                tool_ids=tool_ids,
                tool_names=tool_names,
                was_created=False,
            )

        # Register new server
        # The official @modelcontextprotocol/server-filesystem MCP server
        # provides: read_file, write_file, create_directory, list_directory,
        # move_file, search_files, get_file_info, list_allowed_directories, edit_file
        server = client.mcp_servers.create(
            server_name="filesystem",
            config={
                "mcp_server_type": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", doc_path],
            }
        )

        tool_ids, tool_names = _get_server_tools(client, server.id)
        print(f"Registered Filesystem MCP: {len(tool_ids)} tools")
        return MCPServerInfo(
            name="filesystem",
            server_id=server.id,
            tool_ids=tool_ids,
            tool_names=tool_names,
            was_created=True,
        )

    except Exception as e:
        print(f"Warning: Failed to register Filesystem MCP: {e}")
        return None


def setup_mcp_servers(client: Letta) -> dict[str, MCPServerInfo]:
    """
    Find or register all configured MCP servers with Letta.

    This function is idempotent — existing servers are reused rather than
    duplicated. Each server is conditional on its environment variables being set.

    Args:
        client: Letta client instance

    Returns:
        Dictionary of {server_name: MCPServerInfo} for successfully set up servers
    """
    print("Setting up MCP servers...")
    servers = {}

    # Register each MCP server
    for name, register_fn in [
        ("github", _register_github_mcp),
        ("home-assistant", _register_homeassistant_mcp),
        ("filesystem", _register_filesystem_mcp),
    ]:
        result = register_fn(client)
        if result:
            servers[name] = result

    print(f"MCP setup complete: {len(servers)} servers registered")
    return servers


def get_mcp_tool_ids(servers: dict[str, MCPServerInfo], *server_names: str) -> list[str]:
    """
    Get tool IDs from one or more registered MCP servers.

    Args:
        servers: Dictionary from setup_mcp_servers()
        *server_names: Names of servers to get tools from

    Returns:
        Combined list of tool IDs from all specified servers
    """
    tool_ids = []
    for name in server_names:
        if name in servers:
            tool_ids.extend(servers[name].tool_ids)
    return tool_ids


def get_mcp_tool_names(servers: dict[str, MCPServerInfo], *server_names: str) -> list[str]:
    """
    Get tool names from one or more registered MCP servers.

    Used to build tool rules for MCP tools.

    Args:
        servers: Dictionary from setup_mcp_servers()
        *server_names: Names of servers to get tools from

    Returns:
        Combined list of tool names from all specified servers
    """
    tool_names = []
    for name in server_names:
        if name in servers:
            tool_names.extend(servers[name].tool_names)
    return tool_names
