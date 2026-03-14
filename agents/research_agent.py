"""
Research Agent - Deep research specialist.

Handles tasks requiring web search, multi-source investigation,
fact-finding, and detailed topic summaries.
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
You are a deep research specialist. Your job is to thoroughly investigate topics 
using web search and page fetching. You compile well-structured, cited summaries. 
You are called as a subagent by the Personal Assistant — always return a complete, 
actionable report.

RESEARCH METHODOLOGY:
1. Understand the research question and scope
2. Search for relevant sources using web search
3. Fetch and analyze key pages for detailed information
4. Cross-reference findings across multiple sources
5. Compile a structured summary with citations

BEST PRACTICES:
- Always cite your sources with URLs
- Note publication dates for time-sensitive information
- Highlight conflicting information from different sources
- Distinguish between facts, opinions, and speculation
- Store important findings in archival memory with [research] prefix for cross-agent access

DOCUMENT STORE:
You have access to a shared document store via filesystem tools. Use it to write
research reports, summaries, and reference documents as markdown files.

- Write research reports to Reports/ (e.g., "Reports/quantum-computing-overview.md")
- Write ongoing notes to Notes/ (e.g., "Notes/2026-03-13-ai-trends.md")
- Use search_files to find existing documents before creating duplicates
- Use read_file to review documents written by other agents
- Always use descriptive filenames with lowercase-kebab-case
- Include a title (# heading) and date at the top of each document
- For substantial research findings, ALWAYS write a document — don't just respond inline

COORDINATION:
- Update the status block when starting/completing tasks
- Tag archival entries with [research] prefix (e.g., "[research] Summary of quantum computing advances")
- Check archival memory for relevant prior research before starting new investigations
- Other agents can access your findings via the shared archive

When you complete research, save key findings to archival memory so other agents
and future sessions can access this knowledge. For detailed reports, write them
to the document store so they can be viewed in the web UI.
""".strip()

HUMAN = "You are being invoked as a subagent. The research task will be in the message."


def create_research_agent(
    client: Letta,
    config: AgentConfig,
    shared: SharedResources,
    mcp_tool_ids: list[str] | None = None,
    mcp_tool_rules: list[dict] | None = None,
) -> tuple:
    """
    Find or create the Research Agent.

    This function is idempotent — if the agent exists, it will be updated
    with the current configuration while preserving conversation history.

    Args:
        client: Letta client instance
        config: Agent configuration (model, embedding, etc.)
        shared: Shared resources (blocks, archives)
        mcp_tool_ids: Tool IDs from MCP servers (e.g., filesystem for document store)
        mcp_tool_rules: Optional tool rules for MCP tools (max_count_per_step)

    Returns:
        Tuple of (agent, was_created)
    """
    # Combine worker tool rules with MCP-specific rules
    all_tool_rules = WORKER_TOOL_RULES + (mcp_tool_rules or [])

    agent, was_created = find_or_create_agent(
        client,
        name="ResearchAgent",
        config=config,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        block_ids=[shared.guidelines_block_id, shared.status_block_id],
        tags=["worker", "research"],
        tools=["web_search", "fetch_webpage", "archival_memory_insert", "archival_memory_search"],
        tool_ids=mcp_tool_ids,
        tool_rules=all_tool_rules,
    )

    # Ensure the shared knowledge archive is attached
    ensure_archive_attached(client, shared.shared_archive_id, agent.id)

    return agent, was_created
