"""
Letta Agents Package

Usage:
    from agents import create_all_agents
    agent_ids = create_all_agents()

Or run directly:
    python -m agents.create_all
"""

from .create_all import create_all_agents
from .config import (
    get_config,
    get_client,
    AgentConfig,
    SharedResources,
    create_shared_resources,
    build_mcp_tool_rules,
    find_or_create_agent,
    ensure_archive_attached,
    WORKER_TOOL_RULES,
    SUPERVISOR_TOOL_RULES,
)
from .mcp_setup import setup_mcp_servers, get_mcp_tool_ids, get_mcp_tool_names, MCPServerInfo
from .research_agent import create_research_agent
from .task_agent import create_task_agent
from .coding_agent import create_coding_agent
from .homeassistant_agent import create_homeassistant_agent
from .personal_assistant import create_personal_assistant

__all__ = [
    # Main entry point
    "create_all_agents",
    # Config
    "get_config",
    "get_client",
    "AgentConfig",
    "SharedResources",
    "create_shared_resources",
    "build_mcp_tool_rules",
    "find_or_create_agent",
    "ensure_archive_attached",
    "WORKER_TOOL_RULES",
    "SUPERVISOR_TOOL_RULES",
    # MCP setup
    "setup_mcp_servers",
    "get_mcp_tool_ids",
    "get_mcp_tool_names",
    "MCPServerInfo",
    # Agent creators
    "create_research_agent",
    "create_task_agent",
    "create_coding_agent",
    "create_homeassistant_agent",
    "create_personal_assistant",
]
