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
import time
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


def _find_agent_by_tags(tags):
    """Find an agent matching ALL of the given tags. Returns agent ID or None."""
    query = {"tags": tags, "match_all_tags": "true", "limit": "1"}
    agents = _letta_request("GET", "/v1/agents/", query=query)
    if agents:
        return agents[0]["id"]
    return None


def _find_self_agent_id():
    """Find this agent's own ID by looking for the supervisor/assistant agent."""
    query = {"tags": ["supervisor", "assistant"], "match_all_tags": "true", "limit": "1"}
    agents = _letta_request("GET", "/v1/agents/", query=query)
    if agents:
        return agents[0]["id"]
    return None


def manage_monitoring_task(action: str, task_name: str = "", schedule_cron: str = "", target_agent_tags: str = "", monitoring_prompt: str = "", schedule_id: str = "") -> str:
    """
    Create, list, or delete recurring monitoring tasks scheduled on yourself (the PA).

    When a scheduled monitoring message fires, you will receive it directly and should
    delegate to the appropriate worker via send_message_to_agents_matching_tags, then
    surface results to the user.

    Args:
        action: One of "create", "list", or "delete".
        task_name: A short, unique name for the task (e.g., "house-search", "job-monitor").
                   Required for "create" and "delete".
        schedule_cron: Cron expression for how often to run (e.g., "0 */2 * * *" for every
                       2 hours, "0 9 * * *" for daily at 9am). Required for "create".
        target_agent_tags: Comma-separated tags identifying which worker to delegate to
                          (e.g., "worker,research"). Required for "create".
        monitoring_prompt: The monitoring instructions describing what to search for and
                          the criteria. Required for "create".
        schedule_id: The scheduled message ID to delete. Required for "delete".

    Returns:
        A summary of what was done, including schedule IDs for reference.

    Examples:
        manage_monitoring_task(action="create", task_name="house-search", schedule_cron="0 */2 * * *", target_agent_tags="worker,research", monitoring_prompt="Search Zillow for 3-bed houses under $500k...")
        manage_monitoring_task(action="list")
        manage_monitoring_task(action="delete", task_name="house-search", schedule_id="scheduled_message-abc123")
    """
    try:
        if action == "create":
            if not all([task_name, schedule_cron, target_agent_tags, monitoring_prompt]):
                return "Error: create requires task_name, schedule_cron, target_agent_tags, and monitoring_prompt."

            # Schedule on the PA itself (self) so results flow through Discord directly
            self_agent_id = _find_self_agent_id()
            if not self_agent_id:
                return "Error: Could not find own agent ID (supervisor/assistant tags)."

            tags = [t.strip() for t in target_agent_tags.split(",")]

            # Build the monitoring prompt — the PA receives this and delegates to the worker
            full_prompt = (
                f"[MONITORING TASK: {task_name}] Delegate to worker with tags {tags}:\\n\\n"
                f"{monitoring_prompt}\\n\\n"
                f"DELEGATION INSTRUCTIONS:\\n"
                f"- Use send_message_to_agents_matching_tags to send this task to the worker.\\n"
                f"- Include these instructions for the worker:\\n"
                f"  - Search archival memory for [monitoring:seen:{task_name}] entries to avoid reporting duplicates.\\n"
                f"  - For each NEW result, insert TWO archival entries:\\n"
                f"    1. [monitoring:result:{task_name}] <full details including title, price, link, key attributes>\\n"
                f"    2. [monitoring:seen:{task_name}] <unique identifier like URL or listing ID>\\n"
                f"  - If no new results, say so.\\n"
                f"  - Always include links/URLs.\\n"
                f"- After the worker responds, surface any new/notable results to the user with full details.\\n"
                f"- If the worker found nothing new, briefly note it or stay silent."
            )

            # Create the scheduled message on the PA
            result = _letta_request("POST", f"/v1/agents/{self_agent_id}/schedule", body={
                "messages": [{"role": "user", "content": full_prompt}],
                "schedule": {"type": "recurring", "cron_expression": schedule_cron},
            })

            schedule_id_created = result.get("id", "unknown")
            next_run = result.get("next_scheduled_at", "unknown")

            return (
                f"Monitoring task created successfully.\\n"
                f"  Task name: {task_name}\\n"
                f"  Schedule ID: {schedule_id_created}\\n"
                f"  Scheduled on: self (PA agent {self_agent_id})\\n"
                f"  Delegates to worker with tags: {tags}\\n"
                f"  Cron: {schedule_cron}\\n"
                f"  Next run: {next_run}\\n\\n"
                f"When the schedule fires, you will receive the task directly, "
                f"delegate to the worker, and surface results to the user immediately."
            )

        elif action == "list":
            # Check schedules on the PA itself
            self_agent_id = _find_self_agent_id()
            all_results = []

            if self_agent_id:
                try:
                    data = _letta_request("GET", f"/v1/agents/{self_agent_id}/schedule",
                                          query={"limit": "50"})
                    messages = data.get("scheduled_messages", [])
                    for msg in messages:
                        content = ""
                        msg_data = msg.get("message", {})
                        msgs = msg_data.get("messages", [])
                        if msgs:
                            content = msgs[0].get("content", "")[:100]
                        schedule = msg.get("schedule", {})
                        all_results.append({
                            "schedule_id": msg.get("id", "unknown"),
                            "agent_id": self_agent_id,
                            "agent_label": "PA (self)",
                            "cron": schedule.get("cron_expression", schedule.get("type", "unknown")),
                            "next_run": msg.get("next_scheduled_time", "unknown"),
                            "prompt_preview": content,
                        })
                except Exception:
                    pass

            # Also check legacy worker schedules for backwards compatibility
            for tag_set in [["worker", "research"], ["worker", "task"]]:
                agent_id = _find_agent_by_tags(tag_set)
                if not agent_id:
                    continue
                try:
                    data = _letta_request("GET", f"/v1/agents/{agent_id}/schedule",
                                          query={"limit": "50"})
                    messages = data.get("scheduled_messages", [])
                    for msg in messages:
                        content = ""
                        msg_data = msg.get("message", {})
                        msgs = msg_data.get("messages", [])
                        if msgs:
                            content = msgs[0].get("content", "")[:100]
                        schedule = msg.get("schedule", {})
                        all_results.append({
                            "schedule_id": msg.get("id", "unknown"),
                            "agent_id": agent_id,
                            "agent_label": f"worker ({tag_set})",
                            "cron": schedule.get("cron_expression", schedule.get("type", "unknown")),
                            "next_run": msg.get("next_scheduled_time", "unknown"),
                            "prompt_preview": content,
                        })
                except Exception:
                    continue

            if not all_results:
                return "No active monitoring tasks found."

            lines = ["Active monitoring tasks:\\n"]
            for r in all_results:
                lines.append(
                    f"  - Schedule ID: {r['schedule_id']}\\n"
                    f"    Agent: {r['agent_id']} ({r['agent_label']})\\n"
                    f"    Cron: {r['cron']}\\n"
                    f"    Next run: {r['next_run']}\\n"
                    f"    Prompt: {r['prompt_preview']}...\\n"
                )
            return "\\n".join(lines)

        elif action == "delete":
            if not schedule_id:
                return "Error: delete requires schedule_id. Use action=\\"list\\" to find schedule IDs."

            # Try deleting from PA first, then fall back to workers
            self_agent_id = _find_self_agent_id()
            if self_agent_id:
                try:
                    _letta_request("DELETE", f"/v1/agents/{self_agent_id}/schedule/{schedule_id}")
                    return (
                        f"Monitoring task deleted.\\n"
                        f"  Schedule ID: {schedule_id}\\n"
                        f"  Agent: {self_agent_id} (PA)\\n"
                        f"Note: Historical results in archival memory are preserved."
                    )
                except Exception:
                    pass

            # Fall back to checking worker agents (legacy schedules)
            for tag_set in [["worker", "research"], ["worker", "task"]]:
                agent_id = _find_agent_by_tags(tag_set)
                if not agent_id:
                    continue
                try:
                    _letta_request("DELETE", f"/v1/agents/{agent_id}/schedule/{schedule_id}")
                    return (
                        f"Monitoring task deleted.\\n"
                        f"  Schedule ID: {schedule_id}\\n"
                        f"  Agent: {agent_id} (worker)\\n"
                        f"Note: Historical results in archival memory are preserved."
                    )
                except Exception:
                    continue

            return f"Error: Could not find or delete schedule {schedule_id}. Check the ID with action=\\"list\\"."

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

MONITORING TASKS (via manage_monitoring_task):

Use this tool to set up recurring monitoring jobs. Monitoring tasks are scheduled
on YOU (the PA), not on workers. When a scheduled monitoring message fires, you
receive it directly and delegate to the appropriate worker. See the monitoring
memory block for full instructions on creating, listing, and deleting tasks.

MONITORING TASK MESSAGES:
You will receive [MONITORING TASK: <name>] messages on a schedule. When you do:
1. Delegate the task to the appropriate worker using send_message_to_agents_matching_tags
2. Review the worker's response
3. Surface any new/notable results to the user with full details
4. If nothing new, briefly note it or stay silent

HEARTBEAT MESSAGES:
You will periodically receive [HEARTBEAT] messages. These are your chance to be
proactive. Review your recent context, check your status block, and decide if
anything warrants action or a message to the user. You can:
- Follow up on something discussed earlier
- Check in on delegated tasks
- Surface something you noticed
- Stay silent if nothing needs attention

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

    # Find or create the monitoring task management tool
    existing_monitoring = client.tools.list(name="manage_monitoring_task")
    if existing_monitoring.items:
        monitoring_tool = existing_monitoring.items[0]
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
        block_ids=[shared.guidelines_block_id, shared.status_block_id, shared.monitoring_block_id, shared.notifications_block_id],
        tags=["supervisor", "assistant"],
        # PA can search the shared archive to find prior worker findings
        tools=["web_search", "fetch_webpage", "archival_memory_search"],
        tool_ids=[broadcast_tool.id, coding_tool.id, monitoring_tool.id],
        tool_rules=SUPERVISOR_TOOL_RULES,
    )

    # Ensure the shared knowledge archive is attached
    ensure_archive_attached(client, shared.shared_archive_id, agent.id)

    return agent, was_created
