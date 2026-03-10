"""
Shared configuration for Letta agents.

Environment variables (with defaults):
    LETTA_BASE_URL      - Letta server URL (default: http://localhost:8283)
    LETTA_MODEL         - LLM model to use (default: anthropic/claude-sonnet-4-6)
    LETTA_EMBEDDING     - Embedding model (default: openai/text-embedding-3-small)
"""

import os
from dataclasses import dataclass
from letta_client import Letta


@dataclass
class AgentConfig:
    """Configuration shared across all agents."""
    base_url: str
    model: str
    embedding: str


def get_config() -> AgentConfig:
    """Load configuration from environment variables with defaults."""
    return AgentConfig(
        base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
        model=os.getenv("LETTA_MODEL", "anthropic/claude-sonnet-4-6"),
        embedding=os.getenv("LETTA_EMBEDDING", "letta/letta-free"),
    )


def get_client(config: AgentConfig | None = None) -> Letta:
    """Create a Letta client using the provided or default config."""
    if config is None:
        config = get_config()
    return Letta(base_url=config.base_url)


def get_delegation_tool(client: Letta):
    """
    Fetch the built-in multi-agent delegation tool.

    This tool allows an agent to send a message to another agent
    and wait for its response (synchronous delegation).

    Args:
        client: Letta client instance

    Returns:
        The send_message_to_agent_and_wait_for_reply tool object

    Raises:
        RuntimeError: If the tool is not found on the server
    """
    tools = client.tools.list(name="send_message_to_agent_and_wait_for_reply")
    if not tools.items:
        raise RuntimeError(
            "Multi-agent delegation tool not found. "
            "Ensure your Letta server version supports multi-agent features."
        )
    return tools.items[0]


def get_mcp_tool_ids(client: Letta, server_name: str) -> list[str]:
    """
    Fetch tool IDs from an MCP server by name (case-insensitive partial match).

    This allows agents to use tools provided by MCP servers (e.g., GitHub, Slack).
    Returns an empty list if the server is not found, allowing graceful degradation.

    Args:
        client: Letta client instance
        server_name: Name (or partial name) of the MCP server to match

    Returns:
        List of tool IDs from the matching MCP server, or empty list if not found
    """
    try:
        mcp_servers = client.mcp.list()
        for server in mcp_servers:
            if server_name.lower() in server.server_name.lower():
                # Get tools associated with this MCP server
                tools = client.tools.list(mcp_server_id=server.id)
                tool_ids = [t.id for t in tools]
                return tool_ids
    except Exception as e:
        print(f"Warning: Could not fetch MCP tools for '{server_name}': {e}")
    return []
