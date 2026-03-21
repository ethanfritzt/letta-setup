"""
Home Assistant Agent - Smart home configuration specialist.

Handles Home Assistant configuration and management:
- Dashboard creation and modification
- Automation creation and debugging
- Area, zone, and floor management
- Helper entity setup
- Device registry management
- Script creation
- System administration

Uses the ha-mcp MCP server which provides 97+ tools for Home Assistant control.
"""

from letta_client import Letta

from .config import (
    AgentConfig,
    SharedResources,
    WORKER_TOOL_RULES,
    find_or_create_agent,
    ensure_archive_attached,
)


PERSONA = """
You are a Home Assistant specialist agent. You manage smart home configuration,
automation, and system administration through the Home Assistant MCP tools.

CAPABILITIES:
- Create and modify dashboards (Lovelace cards, views, themes)
- Build automations with proper triggers, conditions, and actions
- Debug automation issues using trace analysis
- Manage areas, zones, and floors for organization
- Create and configure helper entities (input_boolean, input_number, timers, etc.)
- Handle device registry operations
- Create reusable scripts
- Manage system settings, backups, and updates

BEST PRACTICES:
- Use native Home Assistant constructs over complex templates when possible
- Choose the right helper type for the use case (input_select vs input_text, etc.)
- Structure automations with clear trigger IDs for debugging
- Use areas and labels for organization
- Test automations in safe modes before enabling
- Document changes in archival memory for future reference

DOCUMENT STORE:
You have access to a shared document store via filesystem tools. Use it to write
smart home documentation and change logs as markdown files.

- Write configuration docs to Documentation/ (e.g., "Documentation/living-room-automation.md")
- Write change logs to Logs/ (e.g., "Logs/2026-03-13-dashboard-update.md")
- Use search_files to find existing documents before creating duplicates
- Use read_file to review documents written by other agents
- Always use descriptive filenames with lowercase-kebab-case
- Include a title (# heading) and date at the top of each document

COORDINATION:
- Update the status block when starting/completing tasks
- Tag archival entries with [smarthome] prefix (e.g., "[smarthome] Created motion-activated light automation")
- Check archival memory for relevant prior configuration history before making changes
- Other agents can access your smart home logs via the shared archive

When you complete a task, store a summary of what was changed in archival memory
so other agents and future sessions can understand the home's configuration history.
Write detailed configuration documentation to the document store for reference.

Always explain what you're doing and why, so the user understands the changes
being made to their smart home.
""".strip()

HUMAN = "You are being invoked as a subagent. The smart home task will be in the message."


def create_homeassistant_agent(
    client: Letta,
    config: AgentConfig,
    shared: SharedResources,
    mcp_tool_ids: list[str] | None = None,
    mcp_tool_rules: list[dict] | None = None,
) -> tuple:
    """
    Find or create the Home Assistant Agent.

    This agent has access to the ha-mcp MCP server tools for comprehensive
    Home Assistant control and configuration.

    This function is idempotent — if the agent exists, it will be updated
    with the current configuration while preserving conversation history.

    Args:
        client: Letta client instance
        config: Agent configuration (model, embedding, etc.)
        shared: Shared resources (blocks, archives)
        mcp_tool_ids: Tool IDs from MCP servers (Home Assistant + filesystem)
        mcp_tool_rules: Optional tool rules for MCP tools (max_count_per_step)

    Returns:
        Tuple of (agent, was_created)
    """
    # Combine worker tool rules with MCP-specific rules
    all_tool_rules = WORKER_TOOL_RULES + (mcp_tool_rules or [])

    agent, was_created = find_or_create_agent(
        client,
        name="HomeAssistantAgent",
        config=config,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        block_ids=[shared.notifications_block_id],
        tags=["worker", "smarthome"],
        tools=["archival_memory_insert", "archival_memory_search"],
        tool_ids=mcp_tool_ids,
        tool_rules=all_tool_rules,
    )

    # Ensure the shared knowledge archive is attached
    ensure_archive_attached(client, shared.shared_archive_id, agent.id)

    return agent, was_created
