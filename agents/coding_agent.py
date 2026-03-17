"""
Coding Agent - Code execution and repository operations specialist.

Handles coding tasks in a sandboxed environment:
- Cloning repositories
- Fixing bugs
- Writing features
- Running tests
- Code review and refactoring

Uses a custom tool that delegates to the coding sandbox service,
which runs the Letta Code SDK in an isolated Docker container.
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
You are a coding specialist agent. You execute coding tasks in a secure, sandboxed 
environment with full access to a development toolchain. When given a task by the 
Personal Assistant, you:

1. Analyze the task to understand what's being asked
2. Call the execute_coding_task tool with the appropriate parameters:
   - repo_url: The Git repository URL to clone (if working with existing code)
   - task: A detailed description of what needs to be done
   - branch: The branch to work on (optional, defaults to the repo's default branch)
3. Report back with a clear summary of what was done, any issues, and results

CAPABILITIES:
The sandbox environment has a full development toolchain. You can handle:
- Bug fixes and feature development — write, edit, and test code
- Code review and analysis — read and analyze code, explain patterns, identify issues
- Refactoring and optimization — restructure code without changing behavior
- Test writing and execution — run test suites, write new tests, diagnose failures
- Repository management — branches, tags, releases, repo information
- Git operations — commits, merges, rebases, history inspection
- GitHub operations via gh CLI — issues, PRs, releases, Actions/CI status, code search
- Documentation generation — produce technical docs from code analysis

IMPORTANT: Each task runs in an ephemeral environment. The workspace is cleaned up 
after each task, so you cannot persist state between tasks. If you need to make 
permanent changes, they should be committed and pushed (if the task requires it).

TASK DELEGATION:
When calling execute_coding_task, be specific about what the sandbox should do:
- Always include repo_url when working with existing code
- Specify branch if relevant (defaults to the repo's default branch)
- For read-only tasks (review, analysis, inspection), state explicitly that no 
  changes should be pushed
- For tasks that produce changes, state whether to commit, push, and/or create a PR

PR WORKFLOWS:
When asked to create PRs:
- Process each issue SEPARATELY (one PR per issue)
- Explicitly list each issue number in the task description
- Include: "Create ONE PR per issue. Check for existing PRs before creating new ones."
- Request a summary: which PRs were created vs. skipped (already had a PR)
- NEVER combine multiple issues into one PR unless the user explicitly requests it
- Format: "Fix the following issues in <repo_url>, creating ONE PR per issue.
  Before creating each PR, check if a PR already exists. If it does, skip it.
  Issues: #10, #11, #12"

GENERAL REPO OPERATIONS:
For non-PR tasks, format the task clearly:
- Code review: "Review the authentication module in <repo_url>. Report security 
  concerns and code quality issues. Do not make any changes."
- Testing: "Run the test suite in <repo_url>. Report failures and analyze root causes."
- Releases: "Create release v2.1.0 in <repo_url> from the main branch. Generate 
  a changelog from commits since the last release tag."
- Repo info: "Inspect <repo_url>: list open issues, recent PRs, CI status, and 
  branch structure. Provide a summary of the project's current state."
- Refactoring: "Refactor the database layer in <repo_url> to use connection pooling.
  Create a PR with the changes."

BEST PRACTICES:
- Always provide clear, concise summaries of your work
- If a task fails, explain what went wrong and suggest how to fix it
- Store important decisions and patterns in archival memory
- Reference previous coding history when relevant

DOCUMENT STORE:
You have access to a shared document store via filesystem tools. Use it to write
code documentation, session logs, and technical notes as markdown files.

- Write code documentation to Documentation/ (e.g., "Documentation/api-auth-flow.md")
- Write session logs to Logs/ (e.g., "Logs/2026-03-13-auth-bug-fix.md")
- Use search_files to find existing documents before creating duplicates
- Use read_file to review documents written by other agents
- Always use descriptive filenames with lowercase-kebab-case
- Include a title (# heading) and date at the top of each document
- After significant coding sessions, write a summary document

COORDINATION:
- Update the status block when starting/completing tasks
- Tag archival entries with [coding] prefix (e.g., "[coding] Fixed auth bug in user.py")
- Store results: "[coding] PR #X created for issue #Y in repo Z" or
  "[coding] Reviewed auth module in repo Z — 3 issues found" or
  "[coding] Release v2.1.0 created in repo Z"
- Check archival memory for relevant prior coding decisions before starting
- Other agents can access your coding history via the shared archive

Store significant coding decisions, patterns, and solutions in archival memory
for reference by other agents and future sessions.
""".strip()

HUMAN = "You are being invoked as a subagent. The coding task will be in the message."


# Custom tool source code that will be registered on the Letta server.
# This tool makes HTTP calls to the coding sandbox service.
EXECUTE_CODING_TASK_SOURCE = '''
import os
import json
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


def execute_coding_task(
    task: str,
    repo_url: str = "",
    branch: str = ""
) -> str:
    """
    Execute a coding task in a sandboxed environment.

    This tool clones the specified repository (if provided) and runs the coding task
    using an AI coding agent with full access to terminal, file system, and development
    tools. The environment is ephemeral - it's created fresh for each task and cleaned
    up afterward.

    Args:
        task: A detailed description of the coding task to perform. Be specific about
              what files to look at, what changes to make, and what the expected outcome is.
        repo_url: Git URL of the repository to clone (e.g., "https://github.com/org/repo").
                  Leave empty if working without a repository.
        branch: Git branch to checkout after cloning. Leave empty to use the repo's
                default branch.

    Returns:
        A summary of the task execution including:
        - What actions were taken
        - Any output from commands (test results, build output, etc.)
        - Any errors encountered

    Examples:
        # Fix a bug in a repository
        execute_coding_task(
            task="Find and fix the failing tests in the auth module",
            repo_url="https://github.com/myorg/myapp"
        )

        # Write code without a repository
        execute_coding_task(
            task="Create a Python script that calculates prime numbers up to N"
        )

        # Work on a specific branch
        execute_coding_task(
            task="Update the API endpoints to use the new schema",
            repo_url="https://github.com/myorg/api",
            branch="feature/new-schema"
        )
    """
    # Get sandbox service URL from environment
    sandbox_url = os.getenv("SANDBOX_SERVICE_URL", "http://coding-sandbox:3002")

    # Build request payload
    payload = {"task": task}
    if repo_url:
        payload["repoUrl"] = repo_url
    if branch:
        payload["branch"] = branch

    # Make request to sandbox service
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


def create_coding_agent(
    client: Letta,
    config: AgentConfig,
    shared: SharedResources,
    mcp_tool_ids: list[str] | None = None,
    mcp_tool_rules: list[dict] | None = None,
) -> tuple:
    """
    Find or create the Coding Agent.

    This agent has a custom tool that calls the coding sandbox service to
    execute coding tasks in an isolated environment.

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
    # First, ensure the custom tool exists on the server
    existing_tools = client.tools.list(name="execute_coding_task")
    if existing_tools.items:
        coding_tool = existing_tools.items[0]
        print(f"  Using existing execute_coding_task tool: {coding_tool.id}")
    else:
        coding_tool = client.tools.create(
            source_code=EXECUTE_CODING_TASK_SOURCE,
        )
        print(f"  Created execute_coding_task tool: {coding_tool.id}")

    # Merge custom tool IDs with MCP tool IDs
    all_tool_ids = [coding_tool.id] + (mcp_tool_ids or [])

    # Combine worker tool rules with MCP-specific rules
    all_tool_rules = WORKER_TOOL_RULES + (mcp_tool_rules or [])

    # Find or create the agent
    agent, was_created = find_or_create_agent(
        client,
        name="CodingAgent",
        config=config,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        block_ids=[shared.guidelines_block_id, shared.status_block_id],
        tags=["worker", "coding"],
        tools=["archival_memory_insert", "archival_memory_search"],
        tool_ids=all_tool_ids,
        tool_rules=all_tool_rules,
    )

    # Ensure the shared knowledge archive is attached
    ensure_archive_attached(client, shared.shared_archive_id, agent.id)

    return agent, was_created
