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


# Custom tool source code for managing monitoring tasks.
# This tool lets the PA create, list, and delete scheduled monitoring jobs
# on worker agents via the Letta REST API. It uses tag-based agent lookup
# so no agent IDs need to be hardcoded.
MANAGE_MONITORING_TASK_SOURCE = '''
import os
import json
import urllib.parse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def _letta_request(method, path, body=None, query=None):
    """Make a raw HTTP request to the Letta server (stdlib only)."""
    base = os.environ.get("LETTA_BASE_URL", "http://localhost:8283")
    url = base.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)

    headers = {"Content-Type": "application/json"}
    token = os.environ.get("LETTA_API_KEY")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _find_self_agent_id():
    """Find this agent's own ID by looking for the supervisor/assistant agent."""
    query = {"tags": ["supervisor", "assistant"], "match_all_tags": "true", "limit": "1"}
    agents = _letta_request("GET", "/v1/agents/", query=query)
    if agents:
        return agents[0]["id"]
    return None


def _get_monitoring_block(agent_id):
    """Get the monitoring block's ID and parsed JSON data.

    Returns (block_id, data) where data is a dict with a "tasks" key.
    If the block contains non-JSON content (e.g. old instructions),
    returns an empty tasks dict — the caller can overwrite on save.
    """
    blocks = _letta_request("GET", f"/v1/agents/{agent_id}/core-memory/blocks")
    for block in blocks:
        if block.get("label") == "monitoring":
            block_id = block["id"]
            value = block.get("value", "")
            try:
                data = json.loads(value)
                if "tasks" not in data:
                    data["tasks"] = {}
                return block_id, data
            except (json.JSONDecodeError, TypeError):
                return block_id, {"tasks": {}}
    return None, {"tasks": {}}


def _save_monitoring_block(block_id, data):
    """Save monitoring task data back to the block.

    Raises ValueError if the serialized JSON exceeds the safe size limit.
    """
    value = json.dumps(data)
    if len(value) > 4500:
        raise ValueError(
            f"Monitoring block would be {len(value)} chars (limit ~4500). "
            f"Delete some tasks or shorten monitoring prompts."
        )
    _letta_request("PATCH", f"/v1/blocks/{block_id}", body={"value": value})


def manage_monitoring_task(action: str, task_name: str = "", schedule_cron: str = "", target_agent_tags: str = "", monitoring_prompt: str = "") -> str:
    """
    Create, list, or delete recurring monitoring tasks stored in a memory block.

    Monitoring tasks are stored as JSON in the PA's monitoring memory block and
    executed during heartbeats. On each heartbeat, the PA reads the block and
    delegates each task to the appropriate worker.

    Args:
        action: One of "create", "list", or "delete".
        task_name: A short, unique name for the task (e.g., "house-search", "job-monitor").
                   Required for "create" and "delete".
        schedule_cron: Cron expression stored for reference (e.g., "0 */2 * * *").
                       Tasks run on every heartbeat regardless. Required for "create".
        target_agent_tags: Comma-separated tags identifying which worker to delegate to
                          (e.g., "worker,research"). Required for "create".
        monitoring_prompt: The monitoring instructions describing what to search for and
                          the criteria. Required for "create".

    Returns:
        A summary of what was done.

    Examples:
        manage_monitoring_task(action="create", task_name="house-search", schedule_cron="0 */2 * * *", target_agent_tags="worker,research", monitoring_prompt="Search Zillow for 3-bed houses under $500k...")
        manage_monitoring_task(action="list")
        manage_monitoring_task(action="delete", task_name="house-search")
    """
    try:
        if action == "create":
            if not all([task_name, schedule_cron, target_agent_tags, monitoring_prompt]):
                return "Error: create requires task_name, schedule_cron, target_agent_tags, and monitoring_prompt."

            self_agent_id = _find_self_agent_id()
            if not self_agent_id:
                return "Error: Could not find own agent ID (supervisor/assistant tags)."

            block_id, data = _get_monitoring_block(self_agent_id)
            if not block_id:
                return "Error: Could not find monitoring memory block on this agent."

            if task_name in data["tasks"]:
                return f"Error: A monitoring task named \\"{task_name}\\" already exists. Delete it first or use a different name."

            tags = [t.strip() for t in target_agent_tags.split(",")]

            data["tasks"][task_name] = {
                "task_name": task_name,
                "target_agent_tags": tags,
                "monitoring_prompt": monitoring_prompt,
                "cron_expression": schedule_cron,
                "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            }

            try:
                _save_monitoring_block(block_id, data)
            except ValueError as e:
                del data["tasks"][task_name]
                return f"Error: {e}"

            return (
                f"Monitoring task created successfully.\\n"
                f"  Task name: {task_name}\\n"
                f"  Stored in: monitoring memory block\\n"
                f"  Delegates to worker with tags: {tags}\\n"
                f"  Cron (reference): {schedule_cron}\\n\\n"
                f"This task will execute on every heartbeat. The PA reads the monitoring "
                f"block and delegates each task to the appropriate worker."
            )

        elif action == "list":
            self_agent_id = _find_self_agent_id()
            if not self_agent_id:
                return "Error: Could not find own agent ID."

            block_id, data = _get_monitoring_block(self_agent_id)
            if not block_id:
                return "Error: Could not find monitoring memory block."

            tasks = data.get("tasks", {})
            if not tasks:
                return "No active monitoring tasks found."

            lines = [f"Active monitoring tasks ({len(tasks)}):\\n"]
            for name, t in tasks.items():
                lines.append(
                    f"  - Task: {name}\\n"
                    f"    Worker tags: {t.get('target_agent_tags', [])}\\n"
                    f"    Cron (reference): {t.get('cron_expression', 'unknown')}\\n"
                    f"    Created: {t.get('created_at', 'unknown')}\\n"
                    f"    Prompt: {t.get('monitoring_prompt', '')[:100]}...\\n"
                )
            return "\\n".join(lines)

        elif action == "delete":
            if not task_name:
                return "Error: delete requires task_name. Use action=\\"list\\" to find task names."

            self_agent_id = _find_self_agent_id()
            if not self_agent_id:
                return "Error: Could not find own agent ID."

            block_id, data = _get_monitoring_block(self_agent_id)
            if not block_id:
                return "Error: Could not find monitoring memory block."

            if task_name not in data.get("tasks", {}):
                return f"Error: No monitoring task named \\"{task_name}\\" found."

            del data["tasks"][task_name]
            _save_monitoring_block(block_id, data)

            return f"Monitoring task \\"{task_name}\\" deleted from monitoring block."

        else:
            return f"Error: Unknown action \\"{action}\\". Use \\"create\\", \\"list\\", or \\"delete\\"."

    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return f"Letta API error (HTTP {e.code}): {error_body}"
    except URLError as e:
        return f"Could not connect to Letta server: {e.reason}"
    except Exception as e:
        return f"Unexpected error: {str(e)}"
'''


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

You have three ways to handle complex tasks:

1. WORKER AGENTS — delegate via send_message_to_agents_matching_tags
2. CODING SANDBOX — execute directly via execute_coding_task
3. MONITORING TASKS — set up recurring scheduled jobs via manage_monitoring_task

AVAILABLE WORKERS (via send_message_to_agents_matching_tags):

1. Research workers (tags: worker, research)
   - Deep research, web search, fact-finding
   - Multi-source investigation and cited summaries
   - Route: match_all=["worker"], match_some=["research"]

2. Task workers (tags: worker, task)
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
- "Remind me to X / Follow up with Y on Tuesday" -> handle directly (core_memory_append to TODO block)

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

MONITORING TASKS (via manage_monitoring_task):

Use this tool to set up recurring monitoring jobs. Task definitions are stored
in your monitoring memory block as JSON. There is no schedule API — tasks run
on every heartbeat.

When creating a task, provide: task_name, schedule_cron (stored for reference),
target_agent_tags, and monitoring_prompt.

HEARTBEAT MESSAGES:
You will periodically receive [HEARTBEAT] messages. When you do:
1. Check your monitoring block. If it contains tasks (JSON with a non-empty
   "tasks" object), for each task build a delegation message from its
   monitoring_prompt and send it to the worker via
   send_message_to_agents_matching_tags using the task's target_agent_tags.
   Prefix the message with [MONITORING TASK: <task_name>].
   After the worker responds, surface any new results to the user.
2. Check your TODO block. If there are actionable items, pick one and work on it.
3. If there are no monitoring tasks and the TODO block is empty, stay silent.

You and the user can both add items to the TODO block. When the user asks you
to do something later, or you identify a follow-up worth tracking, add it as
a TODO item. Examples:
- "Follow up on research agent's GPU search results"
- "Check PR #42 status and report back"
- "Remind user about meeting prep tomorrow"

REMINDER WORKFLOW:

One-shot reminders ("remind me to X", "follow up with Y on Tuesday") are handled
directly by the PA — do NOT delegate these to the Task Agent.

1. If the user gives no timeframe, ask: "When would you like me to remind you?"
2. Use core_memory_append to add the reminder to the TODO block with a date/time note.
   Format: "[ ] Remind user: <task> — by <date/time>"
3. On every heartbeat, check the TODO block for due reminders and act on them.

TODO block  = one-shot tasks and reminders (checked at every heartbeat)
monitoring  = recurring jobs that run on a cron schedule until deleted

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

    # Find or create the coding sandbox tool (always update source code)
    existing_tools = client.tools.list(name="execute_coding_task")
    if existing_tools.items:
        coding_tool = existing_tools.items[0]
        client.tools.update(coding_tool.id, source_code=EXECUTE_CODING_TASK_SOURCE)
    else:
        coding_tool = client.tools.create(source_code=EXECUTE_CODING_TASK_SOURCE)

    # Find or create the monitoring task management tool (always update source code)
    existing_monitoring = client.tools.list(name="manage_monitoring_task")
    if existing_monitoring.items:
        monitoring_tool = existing_monitoring.items[0]
        client.tools.update(monitoring_tool.id, source_code=MANAGE_MONITORING_TASK_SOURCE)
    else:
        monitoring_tool = client.tools.create(source_code=MANAGE_MONITORING_TASK_SOURCE)

    agent, was_created = find_or_create_agent(
        client,
        name="PersonalAssistant",
        config=config,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        block_ids=[shared.guidelines_block_id, shared.status_block_id, shared.monitoring_block_id, shared.todo_block_id],
        tags=["supervisor", "assistant"],
        # PA can search and write to the shared archive, and edit its own core memory
        tools=["web_search", "fetch_webpage", "archival_memory_search", "archival_memory_insert", "core_memory_append", "core_memory_replace"],
        tool_ids=[broadcast_tool.id, coding_tool.id, monitoring_tool.id],
        tool_rules=SUPERVISOR_TOOL_RULES,
    )

    # Ensure the shared knowledge archive is attached
    ensure_archive_attached(client, shared.shared_archive_id, agent.id)

    return agent, was_created
