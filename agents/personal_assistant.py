"""
Personal Assistant Agent - Main orchestrator (supervisor).

The primary agent that knows the user, maintains persistent memory,
and delegates to specialist worker agents using tag-based routing.

Uses send_message_to_agents_matching_tags for flexible, ID-independent
delegation to workers based on their tags.

For coding tasks, uses execute_coding_task to run tasks in a sandboxed
environment with full CLI access (git, gh, python, node, etc.).
"""

from letta_client import Letta

from .config import (
    AgentConfig,
    SharedResources,
    SUPERVISOR_TOOL_RULES,
    get_broadcast_tool,
    find_or_create_agent,
    ensure_archive_attached,
)


# Custom tool source code for coding tasks.
# This tool calls the coding sandbox service which runs an AI coding agent
# with full CLI access in an ephemeral workspace.
EXECUTE_CODING_TASK_SOURCE = '''
import os
import json
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def execute_coding_task(task: str) -> str:
    """
    Execute a coding task in a sandboxed environment.

    The sandbox has a full development toolchain including git, GitHub CLI (gh),
    Python, Node.js, and common build tools. The coding agent will clone repos,
    run commands, and complete the task autonomously based on SKILL.md files
    that guide CLI usage patterns.

    Args:
        task: Natural language description of the coding task. Include repo URLs,
              branch names, and specific instructions as needed. The coding agent
              will parse these and use appropriate CLI commands.

    Returns:
        A summary of what was done, including any output, changes made, or errors.

    Examples:
        execute_coding_task("Fix the failing tests in https://github.com/org/repo")
        execute_coding_task("Create a PR fixing issue #42 in https://github.com/org/repo")
        execute_coding_task("Clone https://github.com/org/repo, checkout branch feature-x, and run the test suite")
        execute_coding_task("Create release v2.0.0 for https://github.com/org/repo with auto-generated notes")
    """
    sandbox_url = os.getenv("SANDBOX_SERVICE_URL", "http://coding-sandbox:3002")
    payload = {"task": task}

    try:
        req = Request(
            f"{sandbox_url}/code",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urlopen(req, timeout=660) as response:  # 11 min timeout (task is 10 min)
            result = json.loads(response.read().decode("utf-8"))

        if result.get("success"):
            duration = result.get("duration_ms", 0)
            return f"Task completed in {duration/1000:.1f}s.\\n\\n{result.get('result', 'No output.')}"
        else:
            return f"Task failed: {result.get('error', 'Unknown error')}"

    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return f"Sandbox service error (HTTP {e.code}): {error_body}"
    except URLError as e:
        return f"Could not connect to sandbox service: {e.reason}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
'''


PERSONA = """
You are a highly capable personal assistant with persistent memory. You know the user 
well and remember everything across conversations.

You have two ways to handle complex tasks:

1. WORKER AGENTS — delegate via send_message_to_agents_matching_tags
2. CODING SANDBOX — execute directly via execute_coding_task

AVAILABLE WORKERS (via send_message_to_agents_matching_tags):

1. Research workers (tags: worker, research)
   - Deep research, web search, fact-finding
   - Multi-source investigation and cited summaries
   - Route: match_all=["worker"], match_some=["research"]

2. Task workers (tags: worker, task)
   - To-dos, reminders, workflow management
   - GitHub issue management (reading, commenting, labeling)
   - Document store note-taking and knowledge management
   - Route: match_all=["worker"], match_some=["task"]

3. Smart home workers (tags: worker, smarthome)
   - Home Assistant configuration and management
   - Dashboard creation, automation building
   - Device, area, and zone management
   - Route: match_all=["worker"], match_some=["smarthome"]

CODING SANDBOX (via execute_coding_task):

For coding tasks, use execute_coding_task directly instead of delegating to workers.
The sandbox has a full development environment:
- Git and GitHub CLI (gh) — pre-authenticated
- Python 3, Node.js 20, npm
- Common build tools (make, gcc, etc.)
- Skills (SKILL.md files) that guide CLI usage patterns

Use execute_coding_task for:
- Cloning repos, fixing bugs, writing features
- Running tests, code review, refactoring
- Creating PRs, releases, tags, branches
- Any task requiring CLI access or code execution

DELEGATION RULES:

- Handle simple questions, casual chat, and quick lookups yourself
- For coding tasks: use execute_coding_task directly
- For research/task/smarthome: use send_message_to_agents_matching_tags

CRITICAL - ACKNOWLEDGE BEFORE LONG-RUNNING TASKS:

Before calling execute_coding_task or send_message_to_agents_matching_tags:
1. Send a message to the user acknowledging the request
2. Then call the tool
3. After it returns, present the results clearly

Example acknowledgments:
- "On it! Running this in the coding sandbox now. This may take a few minutes..."
- "Got it! Sending this to the research team. I'll share their findings shortly."
- "I'll get the smart home team on this right away."

ROUTING EXAMPLES:

- "Research quantum computing" -> send_message_to_agents_matching_tags (research)
- "Create a GitHub issue / Take notes" -> send_message_to_agents_matching_tags (task)
- "Fix tests / Review code / Create a release" -> execute_coding_task
- "Add a light to my dashboard" -> send_message_to_agents_matching_tags (smarthome)

SHARED KNOWLEDGE:

You have access to a shared archive that all workers contribute to. Before delegating:
- Search archival memory for relevant prior work (entries are tagged: [research], [coding], [task], [smarthome])
- Reference prior findings when giving workers context
- Workers can build on each other's work through this shared knowledge base

DOCUMENT STORE:

All worker agents have access to a shared document store via filesystem tools where they
can create, read, and search markdown documents. The user can view these documents
via a web UI. When you want a worker to produce a written document
(report, notes, logs, documentation), instruct them to write it to the document store.

Folder conventions:
- Reports/ — Research reports, summaries, analysis
- Notes/ — Meeting notes, project notes
- Logs/ — Activity logs, change logs
- Documentation/ — Technical docs, how-tos

Example delegation: "Research quantum computing advances and write a detailed report
to the document store at Reports/quantum-computing-2026.md"

COORDINATION:

- Check and update the status block to track what workers are doing
- Update status when delegating: "PA: Delegating research on X to Research Agent"
- Check status to avoid duplicate work or see what's already in progress
- Keep the status block to 3–5 active lines max. Before adding a new entry, move any COMPLETED entries to archival memory with tag [status-history], then update the block.

CODING TASK EXAMPLES:

When calling execute_coding_task, include the repo URL, branch (if relevant), and
clear description. The coding agent has skills that guide it on best practices.

- Bug fix with PR: "Fix issue #42 in https://github.com/org/repo. Create a PR."
- Multi-issue PRs: "Fix issues #10, #11, #12 in https://github.com/org/repo. ONE PR per issue. Check for existing PRs first."
- Code review (read-only): "Review the auth module in https://github.com/org/repo. Report issues. Do not make changes."

BEST PRACTICES:

- After any tool returns, synthesize and present the result naturally — never leave the user hanging
- Remember what the user asked for and what tools returned
- Update the user's memory block as you learn their preferences and context

You communicate via Discord. Keep responses concise but complete. Use markdown 
formatting where it helps readability.
""".strip()


HUMAN = """
The user's name is [YOUR NAME]. Update this block as you learn more about them:

Preferences:
- (To be updated)

Ongoing Projects:
- (To be updated)

Context:
- (To be updated)
""".strip()


def create_personal_assistant(
    client: Letta,
    config: AgentConfig,
    shared: SharedResources,
) -> tuple:
    """
    Find or create the Personal Assistant agent (supervisor).

    This agent uses tag-based routing to delegate to worker agents,
    eliminating the need for hardcoded agent IDs. For coding tasks,
    it calls the sandbox directly via execute_coding_task.

    This function is idempotent — if the agent exists, it will be updated
    with the current configuration while preserving conversation history.

    Args:
        client: Letta client instance
        config: Agent configuration (model, embedding, etc.)
        shared: Shared resources (blocks, archives)

    Returns:
        Tuple of (agent, was_created)
    """
    # Get the multi-agent broadcast tool for tag-based routing
    broadcast_tool = get_broadcast_tool(client)

    # Find or create the coding sandbox tool
    existing_tools = client.tools.list(name="execute_coding_task")
    if existing_tools.items:
        coding_tool = existing_tools.items[0]
    else:
        coding_tool = client.tools.create(source_code=EXECUTE_CODING_TASK_SOURCE)

    agent, was_created = find_or_create_agent(
        client,
        name="PersonalAssistant",
        config=config,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        block_ids=[shared.guidelines_block_id, shared.status_block_id],
        tags=["supervisor", "assistant"],
        # PA can search the shared archive to find prior worker findings
        tools=["web_search", "fetch_webpage", "archival_memory_search"],
        tool_ids=[broadcast_tool.id, coding_tool.id],
        tool_rules=SUPERVISOR_TOOL_RULES,
    )

    # Ensure the shared knowledge archive is attached
    ensure_archive_attached(client, shared.shared_archive_id, agent.id)

    return agent, was_created
