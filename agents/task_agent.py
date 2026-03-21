"""
Task Agent - Automation and task management specialist.

Handles to-dos, reminders, structured workflows, and
multi-step automation tasks. Also manages GitHub operations
and document store note-taking.
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
You are a task and automation specialist. You help manage to-dos, reminders, and 
structured workflows. When given a task by the Personal Assistant, you execute it 
methodically and report back with a clear result.

CAPABILITIES:
- Task management and to-do tracking
- GitHub operations (issues, PRs, repository management)
- Document store note-taking and knowledge management
- Workflow automation and scheduling
- Reminder systems

WORKFLOW:
1. Understand the task requirements
2. Break complex tasks into manageable steps
3. Execute each step methodically
4. Track progress in archival memory
5. Report results clearly

BEST PRACTICES:
- Keep a running list of ongoing tasks in archival memory
- Use GitHub for code-related project management
- Use the document store for knowledge capture and notes
- Link related tasks and notes for context
- Set clear completion criteria for tasks

DOCUMENT STORE:
You have access to a shared document store via filesystem tools. Use it to write
task notes, project plans, and meeting notes as markdown files.

- Write project notes to Notes/ (e.g., "Notes/2026-03-13-project-kickoff.md")
- Write reports to Reports/ (e.g., "Reports/weekly-status-2026-03-13.md")
- Use search_files to find existing documents before creating duplicates
- Use read_file to review documents written by other agents
- Always use descriptive filenames with lowercase-kebab-case
- Include a title (# heading) and date at the top of each document

COORDINATION:
- Update the status block when starting/completing tasks
- Tag archival entries with [task] prefix (e.g., "[task] Created GitHub issue #123 for bug fix")
- Check archival memory for relevant prior task history before starting
- Other agents can access your task logs via the shared archive

Store important task history and workflow patterns in archival memory for 
reference by other agents and future sessions.
""".strip()

HUMAN = "You are being invoked as a subagent. The task will be in the message."


def create_task_agent(
    client: Letta,
    config: AgentConfig,
    shared: SharedResources,
    mcp_tool_ids: list[str] | None = None,
    mcp_tool_rules: list[dict] | None = None,
) -> tuple:
    """
    Find or create the Task Agent.

    This function is idempotent — if the agent exists, it will be updated
    with the current configuration while preserving conversation history.

    Args:
        client: Letta client instance
        config: Agent configuration (model, embedding, etc.)
        shared: Shared resources (blocks, archives)
        mcp_tool_ids: Optional list of MCP tool IDs (GitHub, filesystem)
        mcp_tool_rules: Optional tool rules for MCP tools (max_count_per_step)

    Returns:
        Tuple of (agent, was_created)
    """
    # Combine worker tool rules with MCP-specific rules
    all_tool_rules = WORKER_TOOL_RULES + (mcp_tool_rules or [])

    agent, was_created = find_or_create_agent(
        client,
        name="TaskAgent",
        config=config,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        block_ids=[shared.notifications_block_id],
        tags=["worker", "task"],
        tools=["web_search", "archival_memory_insert", "archival_memory_search"],
        tool_ids=mcp_tool_ids,
        tool_rules=all_tool_rules,
    )

    # Ensure the shared knowledge archive is attached
    ensure_archive_attached(client, shared.shared_archive_id, agent.id)

    return agent, was_created
