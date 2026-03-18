# Letta Multi-Agent Setup

Docker-based deployment for a Letta multi-agent system with Discord bot interface, featuring:
- **Supervisor-worker orchestration** following Letta best practices
- **Shared knowledge base** across all agents
- **Sandboxed coding execution** via Letta Code SDK
- **MCP integrations** for GitHub, Home Assistant, and a shared document store
- **Document store** via Filesystem MCP for agent-generated documents (pair with SilverBullet or similar for a web UI)

## Architecture

```
User (Discord)
     |
     v
Personal Assistant (supervisor)
  - Handles simple queries directly
  - Delegates to workers via tag-based routing
  - Executes coding tasks directly via sandbox
     |
     +-- Research Agent (tags: worker, research)
     |     - Deep research, web search, fact-finding
     |     - Stores findings with [research] tag
     |
     +-- Task Agent (tags: worker, task)
     |     - To-dos, reminders, workflows
     |     - GitHub operations, document store notes
     |     - Stores entries with [task] tag
     |
     +-- HomeAssistant Agent (tags: worker, smarthome)
     |     - Smart home configuration
     |     - Dashboards, automations, devices
     |     - Stores changes with [smarthome] tag
     |
     +-- [Coding Sandbox - direct tool call]
           - Sandboxed code execution via Letta Code SDK
           - Full CLI: git, gh, python, node, npm
           - Guided by SKILL.md files for CLI patterns
                 |
                 v
           Coding Sandbox Service (Docker)
                 |
                 v
           Letta Code SDK Worker (ephemeral)

Shared Resources:
  - Guidelines block: Coordination rules (all agents)
  - Status block: Task tracking (all agents)  
  - Shared archive: Cross-agent knowledge base
```

## Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.10+** with `pip`
- **Git** with submodule support
- API keys (see Environment Variables below)

## Quick Start

### 1. Clone the repository

```bash
git clone --recurse-submodules https://github.com/YOUR_ORG/letta-setup.git
cd letta-setup
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

### 2. Configure environment

```bash
cp env.template .env
```

Edit `.env` and add your API keys:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
DISCORD_TOKEN=...
DISCORD_APPLICATION_ID=...
DISCORD_PUBLIC_KEY=...

# Set after running agent setup (step 4)
LETTA_AGENT_ID=agent-...
```

### 3. Start services

```bash
docker compose up -d
```

This starts:
- `letta-server` — Letta API server (port 8283)
- `coding-sandbox` — Sandboxed coding environment
- `discord-bot` — Discord interface (will fail until agent ID is set)

Wait for the Letta server to be healthy:

```bash
docker compose logs -f letta-server
# Wait for "Application startup complete"
```

### 4. Set up agents

Install the Letta client and run the setup script:

```bash
pip install letta-client
python -m agents.create_all
```

This creates all agents and shared resources. Copy the printed `LETTA_AGENT_ID` to your `.env` file.

### 5. Restart Discord bot

```bash
docker compose restart discord-bot
```

Your bot is now live! Talk to it on Discord.

## Re-running Setup (Idempotent)

The setup script is **idempotent** — you can run it multiple times safely:

```bash
python -m agents.create_all
```

On re-run:
- **Existing agents are updated** (model, tools, rules) — conversation history preserved
- **Existing shared resources are reused** (blocks, archives, MCP servers)
- **New resources are created only if they don't exist**

This is useful for:
- Applying configuration changes (e.g., new model, updated personas)
- Adding new MCP servers (just set the environment variables and re-run)
- Recovering from partial setup failures

## Services

| Service | Port | Description |
|---------|------|-------------|
| `letta-server` | 8283 | Letta API server |
| `coding-sandbox` | 3002 (internal) | Coding sandbox service |
| `discord-bot` | — | Discord bot interface |

## Agents

| Agent | Tags | Role | Tools |
|-------|------|------|-------|
| **Personal Assistant** | supervisor, assistant | Orchestrator, user-facing | web_search, fetch_webpage, archival_memory_search, send_message_to_agents_matching_tags, execute_coding_task |
| **Research Agent** | worker, research | Deep research | web_search, fetch_webpage, archival_memory_*, Filesystem MCP |
| **Task Agent** | worker, task | Task management | web_search, archival_memory_*, GitHub MCP, Filesystem MCP |
| **HomeAssistant Agent** | worker, smarthome | Smart home config | archival_memory_*, Home Assistant MCP (~97 tools), Filesystem MCP |

The Personal Assistant handles coding tasks directly via `execute_coding_task`, which runs tasks in an isolated sandbox with the Letta Code SDK.

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude models |
| `DISCORD_TOKEN` | Discord bot token |
| `DISCORD_APPLICATION_ID` | Discord application ID |
| `DISCORD_PUBLIC_KEY` | Discord public key |
| `LETTA_AGENT_ID` | Personal Assistant agent ID (from setup script) |

### Optional — Letta Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LETTA_BASE_URL` | `http://localhost:8283` | Letta server URL |
| `LETTA_MODEL` | `anthropic/claude-sonnet-4-6` | LLM model for agents |
| `LETTA_EMBEDDING` | `letta/letta-free` | Embedding model |

### Optional — GitHub Access

| Variable | Description |
|----------|-------------|
| `GH_TOKEN` | GitHub personal access token. Enables private repo access for the coding sandbox (via `gh` CLI) and GitHub MCP tools for the Task Agent. Create at https://github.com/settings/tokens with `repo` scope. |

### Optional — MCP Servers

| Variable | Description |
|----------|-------------|
| `HOMEASSISTANT_MCP_URL` | Home Assistant MCP server URL |
| `HOMEASSISTANT_TOKEN` | Home Assistant long-lived access token |
| `DOCUMENT_STORE_PATH` | Host path to document store directory, mounted into Letta container at `/documents` (default: `./space`) |

### Optional — Coding Sandbox

| Variable | Default | Description |
|----------|---------|-------------|
| `TASK_TIMEOUT_MS` | `600000` | Coding task timeout (10 min) |
| `GIT_COAUTHOR_NAME` | (none) | Your name for commit co-authorship |
| `GIT_COAUTHOR_EMAIL` | (none) | Your email (must match GitHub account for attribution) |

**Commit co-authorship:** When `GIT_COAUTHOR_NAME` and `GIT_COAUTHOR_EMAIL` are set, the sandbox includes a `Co-authored-by` trailer in all git commits. This credits both the bot (primary author) and you (co-author), so commits appear on your GitHub contribution graph.

## Usage Examples

Talk to your Personal Assistant on Discord:

**Research:**
> "Research the latest developments in quantum computing"

**Task management:**
> "Create a GitHub issue for the authentication bug we discussed"

**Coding:**
> "Clone https://github.com/myorg/myapp and fix the failing tests"

**Smart home:**
> "Create an automation that turns on the porch light at sunset"

**Document store:**
> "Research AI trends and write a report to the document store"
> "Take notes on what we discussed today"

The Personal Assistant delegates to worker agents for research, task management, and smart home tasks. For coding tasks, it calls the sandbox directly via `execute_coding_task`.

Worker agents write documents to the shared document store. Pair with [SilverBullet](https://silverbullet.md) or a similar tool to browse them in a web UI.

## Development

### Viewing logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f letta-server
docker compose logs -f discord-bot
```

### Rebuilding after changes

```bash
docker compose build
docker compose up -d
```

### Checking agent status

You can view and manage agents via the Letta ADE at https://app.letta.com (connect to your local server) or via the API.

## Troubleshooting

### Discord bot not responding

1. Check `LETTA_AGENT_ID` is set in `.env`
2. Check bot has proper Discord permissions
3. Check logs: `docker compose logs discord-bot`

### Agent setup fails

1. Ensure Letta server is healthy: `curl http://localhost:8283/v1/health`
2. Check `ANTHROPIC_API_KEY` is valid
3. Re-run setup (it's idempotent)

### Coding tasks timeout

Increase `TASK_TIMEOUT_MS` in `.env` (default is 10 minutes).

## License

MIT
