#!/usr/bin/env python3
"""
Letta Agent Setup Script

Sets up all agents and shared resources in the correct order:
  1. Register MCP servers (GitHub, Home Assistant, Obsidian)
  2. Create shared memory blocks and archives
  3. Create worker agents (Research, Task, Coding, HomeAssistant)
  4. Create Personal Assistant (supervisor with tag-based routing)

This script is IDEMPOTENT — it can be run multiple times safely:
  - Existing agents are updated (config changes applied, history preserved)
  - Existing shared resources are reused (blocks, archives, MCP servers)
  - New resources are created only if they don't exist

The Personal Assistant uses tag-based routing instead of hardcoded agent IDs,
making the system resilient to agent recreation.

Usage:
    python -m agents.create_all
    # or
    python agents/create_all.py

Environment variables:
    LETTA_BASE_URL          - Letta server URL (default: http://localhost:8283)
    LETTA_MODEL             - LLM model (default: anthropic/claude-sonnet-4-6)
    LETTA_EMBEDDING         - Embedding model (default: letta/letta-free)
    GH_TOKEN                - GitHub personal access token (optional)
    HOMEASSISTANT_MCP_URL   - Home Assistant MCP server URL (optional)
    HOMEASSISTANT_TOKEN     - Home Assistant long-lived access token (optional)
    OBSIDIAN_VAULT_PATH     - Path to Obsidian vault (optional)
"""

from .config import get_config, get_client, create_shared_resources, build_mcp_tool_rules
from .mcp_setup import setup_mcp_servers, get_mcp_tool_ids, get_mcp_tool_names
from .research_agent import create_research_agent
from .task_agent import create_task_agent
from .coding_agent import create_coding_agent
from .homeassistant_agent import create_homeassistant_agent
from .personal_assistant import create_personal_assistant


def _status(was_created: bool) -> str:
    """Return status string for created vs updated resources."""
    return "created" if was_created else "updated"


def create_all_agents():
    """
    Set up all agents and shared resources (idempotent).

    This function can be run multiple times safely. Existing resources
    are reused/updated rather than duplicated.

    Order:
    1. Register MCP servers (GitHub, Home Assistant, Obsidian)
    2. Create shared memory blocks and archives
    3. Create worker agents (tags allow PA to discover them)
    4. Create Personal Assistant supervisor

    Returns:
        dict: Dictionary with agent IDs keyed by role name
    """
    config = get_config()
    client = get_client(config)

    print(f"Connecting to Letta at {config.base_url}")
    print(f"Using model: {config.model}")
    print(f"Using embedding: {config.embedding}")
    print()

    # =========================================================================
    # Step 1: Register MCP servers (idempotent)
    # =========================================================================
    mcp_servers = setup_mcp_servers(client)
    print()

    # Get tool IDs and names for each agent
    # Task Agent gets GitHub + Obsidian
    task_mcp_tools = get_mcp_tool_ids(mcp_servers, "github", "obsidian")
    task_mcp_tool_names = get_mcp_tool_names(mcp_servers, "github", "obsidian")
    task_mcp_rules = build_mcp_tool_rules(task_mcp_tool_names, max_count=5)

    # HomeAssistant Agent gets HA MCP tools
    ha_mcp_tools = get_mcp_tool_ids(mcp_servers, "home-assistant")
    ha_mcp_tool_names = get_mcp_tool_names(mcp_servers, "home-assistant")
    ha_mcp_rules = build_mcp_tool_rules(ha_mcp_tool_names, max_count=5)

    # =========================================================================
    # Step 2: Create shared resources (idempotent)
    # =========================================================================
    shared = create_shared_resources(client)
    print()

    # =========================================================================
    # Step 3: Create worker agents (idempotent)
    # =========================================================================
    print("Setting up worker agents...")

    research_agent, research_created = create_research_agent(client, config, shared)
    print(f"  Research Agent {_status(research_created)}:      {research_agent.id}")

    task_agent, task_created = create_task_agent(
        client, config, shared,
        mcp_tool_ids=task_mcp_tools,
        mcp_tool_rules=task_mcp_rules,
    )
    print(f"  Task Agent {_status(task_created)}:          {task_agent.id}")

    coding_agent, coding_created = create_coding_agent(client, config, shared)
    print(f"  Coding Agent {_status(coding_created)}:        {coding_agent.id}")

    homeassistant_agent, ha_created = create_homeassistant_agent(
        client, config, shared,
        mcp_tool_ids=ha_mcp_tools,
        mcp_tool_rules=ha_mcp_rules,
    )
    print(f"  HomeAssistant Agent {_status(ha_created)}: {homeassistant_agent.id}")

    print()

    # =========================================================================
    # Step 4: Create supervisor (Personal Assistant) (idempotent)
    # =========================================================================
    print("Setting up supervisor agent...")

    personal_assistant, pa_created = create_personal_assistant(client, config, shared)
    print(f"  Personal Assistant {_status(pa_created)}:  {personal_assistant.id}")

    print()

    # =========================================================================
    # Summary
    # =========================================================================
    print("=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print()
    print("Agent IDs:")
    print(f"  Personal Assistant:  {personal_assistant.id}")
    print(f"  Research Agent:      {research_agent.id}")
    print(f"  Task Agent:          {task_agent.id}")
    print(f"  Coding Agent:        {coding_agent.id}")
    print(f"  HomeAssistant Agent: {homeassistant_agent.id}")
    print()
    print("MCP Servers:")
    if mcp_servers:
        for name, info in mcp_servers.items():
            status = "new" if info.was_created else "existing"
            print(f"  {name}: {len(info.tool_ids)} tools ({status})")
    else:
        print("  (none configured)")
    print()
    print("For your Discord bot .env file:")
    print(f'  LETTA_AGENT_ID="{personal_assistant.id}"')
    print()
    print("This script is idempotent — run it again to update agent configs.")
    print("Conversation history and archival memory are preserved on re-run.")
    print("=" * 60)

    return {
        "personal_assistant": personal_assistant.id,
        "research_agent": research_agent.id,
        "task_agent": task_agent.id,
        "coding_agent": coding_agent.id,
        "homeassistant_agent": homeassistant_agent.id,
    }


if __name__ == "__main__":
    create_all_agents()
