"""
Shared configuration for Letta agents.

Environment variables (with defaults):
    LETTA_BASE_URL      - Letta server URL (default: http://localhost:8283)
    LETTA_MODEL         - LLM model to use (default: anthropic/claude-sonnet-4-6)
    LETTA_EMBEDDING     - Embedding model (default: ollama/mxbai-embed-large:latest)

Per-agent model overrides (each falls back to LETTA_MODEL if not set):
    LETTA_MODEL_PA            - Model for the Personal Assistant agent
    LETTA_MODEL_RESEARCH      - Model for the Research agent
    LETTA_MODEL_TASK          - Model for the Task agent
    LETTA_MODEL_CODING        - Model for the Coding agent
    LETTA_MODEL_HOMEASSISTANT - Model for the HomeAssistant agent

Use get_agent_model(agent_key, config) to resolve a per-agent override with
automatic fallback to the global LETTA_MODEL default.
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


@dataclass
class SharedResources:
    """Shared memory blocks and archives for cross-agent coordination."""
    guidelines_block_id: str
    status_block_id: str
    monitoring_block_id: str
    todo_block_id: str
    shared_archive_id: str


# Standard tool rules for worker agents (per Letta docs)
WORKER_TOOL_RULES = [
    {
        "tool_name": "archival_memory_insert",
        "type": "max_count_per_step",
        "max_count_limit": 2
    },
    {
        "tool_name": "archival_memory_search",
        "type": "max_count_per_step",
        "max_count_limit": 2
    },
]

# Tool rules for supervisor agents (higher limit for delegation)
SUPERVISOR_TOOL_RULES = [
    {
        "tool_name": "send_message_to_agents_matching_tags",
        "type": "max_count_per_step",
        "max_count_limit": 10
    },
]


def get_config() -> AgentConfig:
    """
    Load configuration from environment variables with defaults.

    For per-agent model overrides, use get_agent_model(agent_key, config)
    after calling this function.
    """
    return AgentConfig(
        base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
        model=os.getenv("LETTA_MODEL", "anthropic/claude-sonnet-4-6"),
        embedding=os.getenv("LETTA_EMBEDDING", "ollama/mxbai-embed-large:latest"),
    )


def get_agent_model(agent_key: str, config: AgentConfig) -> str:
    """
    Get the LLM model for a specific agent, falling back to the global default.

    Reads the per-agent env var ``LETTA_MODEL_<AGENT_KEY>`` (e.g.
    ``LETTA_MODEL_CODING`` for ``agent_key="coding"``). If the variable is not
    set the value of ``config.model`` (i.e. the global ``LETTA_MODEL`` default)
    is returned unchanged, so this function is fully backwards compatible.

    Args:
        agent_key: Agent identifier. One of "pa", "research", "task",
                   "coding", "homeassistant".
        config: AgentConfig instance returned by get_config().

    Returns:
        The model string to use for this agent.

    Example::

        config = get_config()
        model = get_agent_model("coding", config)
        # → value of LETTA_MODEL_CODING, or config.model if not set
    """
    return os.getenv(f"LETTA_MODEL_{agent_key.upper()}", config.model)


def get_client(config: AgentConfig | None = None) -> Letta:
    """Create a Letta client using the provided or default config."""
    if config is None:
        config = get_config()
    return Letta(base_url=config.base_url)


def get_broadcast_tool(client: Letta):
    """
    Fetch the built-in multi-agent broadcast tool for tag-based routing.

    This tool allows an agent to send a message to agents matching specific tags
    and wait for their responses (synchronous broadcast).

    Args:
        client: Letta client instance

    Returns:
        The send_message_to_agents_matching_tags tool object

    Raises:
        RuntimeError: If the tool is not found on the server
    """
    tools = client.tools.list(name="send_message_to_agents_matching_tags")
    if not tools.items:
        raise RuntimeError(
            "Multi-agent broadcast tool not found. "
            "Ensure your Letta server version supports multi-agent features."
        )
    return tools.items[0]


# =============================================================================
# Find-or-create helpers for idempotent setup
# =============================================================================

def find_or_create_block(
    client: Letta,
    label: str,
    description: str,
    default_value: str,
) -> tuple[str, bool]:
    """
    Find an existing block by label or create a new one.

    If a block with the given label exists, its ID is returned without
    modifying its value (preserving user customizations).

    Args:
        client: Letta client instance
        label: Block label to search for
        description: Description for new block (ignored if exists)
        default_value: Initial value for new block (ignored if exists)

    Returns:
        Tuple of (block_id, was_created)
    """
    existing = client.blocks.list(label=label)
    if existing.items:
        return existing.items[0].id, False

    block = client.blocks.create(
        label=label,
        description=description,
        value=default_value,
    )
    return block.id, True


def find_or_create_archive(
    client: Letta,
    name: str,
    description: str,
) -> tuple[str, bool]:
    """
    Find an existing archive by name or create a new one.

    Args:
        client: Letta client instance
        name: Archive name to search for
        description: Description for new archive (ignored if exists)

    Returns:
        Tuple of (archive_id, was_created)
    """
    existing = client.archives.list(name=name)
    if existing.items:
        return existing.items[0].id, False

    archive = client.archives.create(name=name, description=description)
    return archive.id, True


def find_or_create_agent(
    client: Letta,
    name: str,
    config: AgentConfig,
    memory_blocks: list[dict],
    block_ids: list[str],
    tags: list[str],
    tools: list[str],
    tool_ids: list[str] | None = None,
    tool_rules: list[dict] | None = None,
) -> tuple[object, bool]:
    """
    Find an existing agent by name or create a new one.

    If the agent exists, it is updated with the new configuration
    (model, tags, tools, tool_rules, block_ids). Conversation history
    and archival memory are preserved.

    Args:
        client: Letta client instance
        name: Agent name to search for
        config: Agent configuration (model, embedding)
        memory_blocks: Agent's core memory blocks (persona, human)
        block_ids: IDs of shared blocks to attach
        tags: Agent tags for discovery
        tools: Built-in tool names
        tool_ids: Custom/MCP tool IDs (optional)
        tool_rules: Tool usage rules (optional)

    Returns:
        Tuple of (agent, was_created)
    """
    existing = client.agents.list(name=name)
    if existing.items:
        agent = existing.items[0]
        # Fetch the agent's current block IDs (includes persona, human, etc.)
        # so that passing block_ids to agents.update() doesn't evict them.
        # agents.update(block_ids=...) replaces the full block list, so we
        # must merge the agent's own blocks with the incoming shared block IDs.
        current_blocks = client.agents.blocks.list(agent.id)
        current_block_ids = [b.id for b in current_blocks.items]
        merged_block_ids = list({*current_block_ids, *block_ids})

        # Update existing agent with new configuration
        client.agents.update(
            agent.id,
            model=config.model,
            embedding=config.embedding,
            tags=tags,
            tool_ids=tool_ids or [],
            tool_rules=tool_rules or [],
            block_ids=merged_block_ids,
        )
        # Re-attach tools (update replaces, so we need to ensure all tools are set)
        # Note: built-in tools like "web_search" are specified by name in create,
        # but update uses tool_ids. We'll handle this by ensuring the agent
        # has the tools it needs through the update's tool_ids parameter.
        # For built-in tools, we need to look them up and add their IDs.
        builtin_tool_ids = []
        for tool_name in tools:
            tool_list = client.tools.list(name=tool_name)
            if tool_list.items:
                builtin_tool_ids.append(tool_list.items[0].id)

        all_tool_ids = builtin_tool_ids + (tool_ids or [])
        if all_tool_ids:
            client.agents.update(agent.id, tool_ids=all_tool_ids)

        # Update memory blocks (persona, human) to apply any prompt changes
        # Get the agent's current blocks and update them by label
        agent_blocks = client.agents.blocks.list(agent.id)
        for block_def in memory_blocks:
            label = block_def["label"]
            new_value = block_def["value"]
            # Find the matching block by label and update it
            for block in agent_blocks.items:
                if block.label == label:
                    client.blocks.update(block.id, value=new_value)
                    break

        # Refresh agent state after update
        agent = client.agents.retrieve(agent.id)
        return agent, False

    # Create new agent
    agent = client.agents.create(
        name=name,
        model=config.model,
        embedding=config.embedding,
        memory_blocks=memory_blocks,
        block_ids=block_ids,
        tags=tags,
        tools=tools,
        tool_ids=tool_ids or [],
        tool_rules=tool_rules or [],
    )
    return agent, True


def ensure_archive_attached(client: Letta, archive_id: str, agent_id: str) -> None:
    """
    Ensure an archive is attached to an agent (idempotent).

    Attempts to attach the archive. If already attached, the API typically
    handles this gracefully (no-op or returns success).

    Args:
        client: Letta client instance
        archive_id: ID of the archive to attach
        agent_id: ID of the agent
    """
    try:
        client.agents.archives.attach(archive_id, agent_id=agent_id)
    except Exception:
        # Archive may already be attached; that's fine
        pass


# =============================================================================
# Shared resource creation (idempotent)
# =============================================================================

# Default values for shared blocks
GUIDELINES_DEFAULT = """Coordination Guidelines:
- Communicate through the Personal Assistant for user-facing responses
- Store important findings in shared archival memory with domain tags
- Update the status block when starting/completing tasks
- Report task results clearly and concisely
- Flag any errors or blockers immediately

Document Store:
All worker agents have access to a shared document store via filesystem tools.
Documents are markdown files stored in the shared document store.

Folder conventions (content-type based):
- Reports/     — Research reports, summaries, analysis documents
- Notes/       — Meeting notes, project notes, ongoing observations
- Logs/        — Activity logs, change logs, session summaries
- Documentation/ — Technical docs, how-tos, configuration references

File naming: lowercase-kebab-case with dates where relevant
  e.g., "Reports/quantum-computing-overview.md"
  e.g., "Logs/2026-03-13-dashboard-update.md"

Each document should start with a # heading and include the date.
Use search_files before creating a document to avoid duplicates.
Agents can read each other's documents for cross-agent context.

User Preferences:
- (Updated by Personal Assistant as user preferences are learned)
""".strip()

STATUS_DEFAULT = """# Keep this block to 3–5 active lines. Archive completed entries to archival memory (tag: status-history) before adding new ones.
Task Status:
- (Agents update this block when starting/completing tasks)

Recent Activity:
- (System initialized)
""".strip()

MONITORING_DEFAULT = '{"tasks": {}}'


TODO_DEFAULT = """# TODO / Roadmap
Items here guide what the PA works on during heartbeats.
The PA and user can both add items. Mark items [DONE] when complete,
then archive to archival memory (tag: todo-history).
Keep to 5-10 active items max.

Active:
- (No items yet — PA stays silent during heartbeats until items are added)
""".strip()


def create_shared_blocks(client: Letta) -> dict[str, str]:
    """
    Find or create shared memory blocks for cross-agent coordination.

    Creates (if not existing):
    - Guidelines block: Coordination rules and user preferences
    - Status block: Current task states for coordination

    If blocks already exist, their values are preserved.

    Args:
        client: Letta client instance

    Returns:
        Dictionary mapping block labels to their IDs
    """
    guidelines_id, guidelines_created = find_or_create_block(
        client,
        label="guidelines",
        description="Shared guidelines and user context across all agents",
        default_value=GUIDELINES_DEFAULT,
    )
    status = "Created" if guidelines_created else "Found existing"
    print(f"{status} shared guidelines block: {guidelines_id}")

    status_id, status_created = find_or_create_block(
        client,
        label="status",
        description="Current task status for cross-agent coordination",
        default_value=STATUS_DEFAULT,
    )
    status = "Created" if status_created else "Found existing"
    print(f"{status} shared status block: {status_id}")

    monitoring_id, monitoring_created = find_or_create_block(
        client,
        label="monitoring",
        description="JSON registry of active monitoring tasks",
        default_value=MONITORING_DEFAULT,
    )
    status = "Created" if monitoring_created else "Found existing"
    print(f"{status} shared monitoring block: {monitoring_id}")

    todo_id, todo_created = find_or_create_block(
        client,
        label="todo",
        description="TODO list guiding PA heartbeat actions",
        default_value=TODO_DEFAULT,
    )
    status = "Created" if todo_created else "Found existing"
    print(f"{status} shared todo block: {todo_id}")

    return {
        "guidelines": guidelines_id,
        "status": status_id,
        "monitoring": monitoring_id,
        "todo": todo_id,
    }


def create_shared_archive(client: Letta) -> str:
    """
    Find or create the shared archive for cross-agent knowledge.

    All agents (PA and workers) share this archive. Workers tag their entries
    with domain prefixes (e.g., [research], [coding]) for organization.

    If the archive already exists, its ID is returned (contents preserved).

    Args:
        client: Letta client instance

    Returns:
        The shared archive ID
    """
    archive_id, created = find_or_create_archive(
        client,
        name="shared_knowledge",
        description=(
            "Shared knowledge base for all agents. "
            "Entries are tagged by domain: [research], [coding], [task], [smarthome]."
        ),
    )
    status = "Created" if created else "Found existing"
    print(f"{status} shared archive 'shared_knowledge': {archive_id}")
    return archive_id


def create_shared_resources(client: Letta) -> SharedResources:
    """
    Find or create all shared resources (blocks and archives) for the agent system.

    This function is idempotent — running it multiple times will reuse
    existing resources rather than creating duplicates.

    Args:
        client: Letta client instance

    Returns:
        SharedResources object with all resource IDs
    """
    print("Setting up shared resources...")

    blocks = create_shared_blocks(client)
    archive_id = create_shared_archive(client)

    return SharedResources(
        guidelines_block_id=blocks["guidelines"],
        status_block_id=blocks["status"],
        monitoring_block_id=blocks["monitoring"],
        todo_block_id=blocks["todo"],
        shared_archive_id=archive_id,
    )


def build_mcp_tool_rules(tool_names: list[str], max_count: int = 5) -> list[dict]:
    """
    Build tool rules to limit MCP tool calls per step.

    This prevents runaway behavior where an agent calls external MCP tools
    excessively in a single step.

    Args:
        tool_names: List of MCP tool names to create rules for
        max_count: Maximum calls per tool per step (default: 5)

    Returns:
        List of tool rule dictionaries
    """
    return [
        {
            "tool_name": name,
            "type": "max_count_per_step",
            "max_count_limit": max_count,
        }
        for name in tool_names
    ]
