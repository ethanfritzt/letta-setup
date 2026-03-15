/**
 * Coding Sandbox Service
 *
 * Express server that accepts coding tasks, clones repositories into
 * ephemeral workspaces, and executes them using the Letta Code SDK.
 *
 * The Letta Code worker agent is integrated into the Letta hierarchy via
 * shared memory blocks (guidelines, status) queried from the Letta API
 * at startup. After each task, the worker's message history is reset to
 * keep context clean between tasks.
 *
 * Custom skills (e.g., github-cli) are copied into each workspace's
 * .skills/ directory so Letta Code discovers them automatically.
 *
 * Endpoints:
 *   POST /code - Execute a coding task
 *   GET /health - Health check
 */

import express, { Request, Response } from "express";
import { createAgent, createSession } from "@letta-ai/letta-code-sdk";
import { execSync } from "child_process";
import { mkdtempSync, rmSync, existsSync, cpSync, mkdirSync } from "fs";
import path from "path";

const app = express();
app.use(express.json({ limit: "10mb" }));

const PORT = process.env.PORT || 3002;
const WORKSPACE_ROOT = process.env.WORKSPACE_ROOT || "/workspace";
const TASK_TIMEOUT_MS = parseInt(process.env.TASK_TIMEOUT_MS || "600000", 10);
const LETTA_BASE_URL = process.env.LETTA_BASE_URL || "http://letta-server:8283";
const SKILLS_SOURCE = process.env.SKILLS_SOURCE || "/app/skills";

// =============================================================================
// Letta REST API Helpers
// =============================================================================

/**
 * Helper to make requests to the Letta API, following redirects.
 *
 * The Letta server may return 307 redirects (e.g., /v1/blocks → /v1/blocks/),
 * so we always use redirect: "follow" (Node.js fetch default) and add
 * trailing slashes to avoid unnecessary redirects.
 */
async function lettaApi(
  path: string,
  options: RequestInit = {}
): Promise<globalThis.Response> {
  const url = `${LETTA_BASE_URL}${path}`;
  return fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
}

interface SharedBlockIds {
  guidelinesBlockId: string | null;
  statusBlockId: string | null;
}

/**
 * Query the Letta API to find shared block IDs by label.
 *
 * These are the same blocks used by your Letta hierarchy agents
 * (PersonalAssistant, CodingAgent, etc.). By attaching them to
 * the Letta Code worker, it shares state with the rest of the system.
 */
async function discoverSharedBlocks(): Promise<SharedBlockIds> {
  const result: SharedBlockIds = {
    guidelinesBlockId: null,
    statusBlockId: null,
  };

  for (const label of ["guidelines", "status"] as const) {
    try {
      const response = await lettaApi(`/v1/blocks/?label=${label}&limit=1`);

      if (response.ok) {
        const data = await response.json() as { items?: Array<{ id: string }> };
        // API may return { items: [...] } or just [...]
        const items = data.items || (Array.isArray(data) ? data : []);
        if (items.length > 0) {
          const key = `${label}BlockId` as keyof SharedBlockIds;
          result[key] = items[0].id;
          console.log(`Found shared ${label} block: ${items[0].id}`);
        } else {
          console.warn(`No shared ${label} block found in Letta server`);
        }
      } else {
        console.warn(`Failed to query ${label} block: HTTP ${response.status}`);
      }
    } catch (error) {
      console.warn(`Could not query ${label} block:`, error);
    }
  }

  return result;
}

// =============================================================================
// Letta Code Worker Agent Management
// =============================================================================

/**
 * Cached worker agent ID. Created once, reused across tasks.
 * Each task gets a fresh conversation via createSession() for clean context.
 */
let codingWorkerId: string | null = null;
let sharedBlocks: SharedBlockIds | null = null;

const WORKER_PERSONA = `You are a coding execution agent integrated into a team of specialist agents.

You have access to shared guidelines and status blocks that coordinate work across the team.
Update the status block when starting and completing tasks.

You have skills loaded that teach you how to use specific tools (like the GitHub CLI).
Always check your available skills when working with external tools.

When working on coding tasks:
- Follow the patterns and rules defined in your loaded skills
- Report results clearly with status (CREATED, SKIPPED, FAILED)
- Store important decisions in memory for future reference`;

/**
 * Get or create the persistent Letta Code worker agent.
 *
 * The worker is created once with shared blocks from the Letta hierarchy,
 * then reused. Each task gets a fresh conversation via createSession().
 *
 * Validates the cached agent ID still exists on the Letta server before
 * returning it — handles cases where the agent was deleted (e.g., after
 * a server database reset or manual cleanup).
 *
 * IMPORTANT: Shared blocks are always re-discovered when creating a new
 * agent to avoid using stale block IDs from deleted/recreated blocks.
 */
async function getOrCreateWorker(): Promise<string> {
  if (codingWorkerId) {
    // Validate the cached agent still exists on the Letta server
    try {
      const resp = await lettaApi(`/v1/agents/${codingWorkerId}`);
      if (resp.ok) {
        return codingWorkerId;
      }
      console.warn(`Cached worker agent ${codingWorkerId} no longer exists (HTTP ${resp.status}), recreating...`);
    } catch (error) {
      console.warn(`Failed to validate cached worker agent ${codingWorkerId}:`, error);
    }
    codingWorkerId = null;
  }

  // Always re-discover shared blocks when creating a new agent.
  // This ensures we pick up new block IDs if blocks were deleted and recreated.
  sharedBlocks = await discoverSharedBlocks();

  // Build memory blocks: persona + shared blocks from hierarchy
  const memory: Array<{ label: string; value: string } | { blockId: string }> = [
    { label: "persona", value: WORKER_PERSONA },
    { label: "human", value: "Tasks are dispatched by the Coding Agent in the Letta hierarchy." },
  ];

  if (sharedBlocks.guidelinesBlockId) {
    memory.push({ blockId: sharedBlocks.guidelinesBlockId });
  }
  if (sharedBlocks.statusBlockId) {
    memory.push({ blockId: sharedBlocks.statusBlockId });
  }

  console.log("Creating Letta Code worker agent...");
  console.log(`  Shared blocks: guidelines=${sharedBlocks.guidelinesBlockId || "none"}, status=${sharedBlocks.statusBlockId || "none"}`);

  codingWorkerId = await createAgent({
    memory,
    tags: ["worker", "coding", "executor"],
    memfs: false,
    skillSources: ["project"],
  });

  console.log(`Created Letta Code worker: ${codingWorkerId}`);
  return codingWorkerId;
}

// Note: resetWorkerMessages was removed. Each task now gets a fresh
// conversation via createSession(agentId), which is the documented Letta
// pattern for isolating task context while preserving agent memory.

// =============================================================================
// Skills Management
// =============================================================================

/**
 * Copy skills from the image into the workspace's .skills/ directory.
 *
 * Letta Code discovers project-scoped skills from .skills/ relative to cwd.
 * The skills are baked into the Docker image at /app/skills/ and copied
 * into each ephemeral workspace so the agent can discover them.
 */
function copySkillsToWorkspace(workdir: string): void {
  if (!existsSync(SKILLS_SOURCE)) {
    console.warn(`Skills source not found: ${SKILLS_SOURCE}`);
    return;
  }

  const targetDir = path.join(workdir, ".skills");
  try {
    mkdirSync(targetDir, { recursive: true });
    cpSync(SKILLS_SOURCE, targetDir, { recursive: true });
    console.log(`Copied skills to ${targetDir}`);
  } catch (error) {
    console.warn("Failed to copy skills to workspace:", error);
  }
}

// =============================================================================
// Task Execution
// =============================================================================

interface CodeRequest {
  repoUrl?: string;
  task: string;
  branch?: string;
}

interface CodeResponse {
  success: boolean;
  result?: string;
  error?: string;
  duration_ms?: number;
}

/**
 * Clone a git repository into the specified directory.
 *
 * Uses `gh repo clone` instead of `git clone` so that the GH_TOKEN
 * environment variable is used automatically for authentication.
 * This is required for private repositories and avoids interactive
 * credential prompts that fail in non-interactive sandbox environments.
 *
 * Falls back to `git clone` for non-GitHub URLs.
 */
function cloneRepo(repoUrl: string, targetDir: string, branch?: string): void {
  console.log(`Cloning ${repoUrl}${branch ? ` (branch: ${branch})` : ""} into ${targetDir}`);

  // Extract owner/repo from GitHub URLs (HTTPS or SSH)
  const match = repoUrl.match(/github\.com[/:]([^/]+\/[^/.]+?)(?:\.git)?$/);

  if (match) {
    // Use gh repo clone for GitHub repos (handles auth via GH_TOKEN)
    const ownerRepo = match[1];
    const gitFlags = ["--depth", "1"];
    if (branch) {
      gitFlags.push("-b", branch);
    }

    execSync(`gh repo clone ${ownerRepo} ${targetDir} -- ${gitFlags.join(" ")}`, {
      timeout: 120000,
      stdio: "pipe",
    });
  } else {
    // Fallback to git clone for non-GitHub URLs
    const args = ["clone", "--depth", "1"];
    if (branch) {
      args.push("-b", branch);
    }
    args.push(repoUrl, targetDir);

    execSync(`git ${args.join(" ")}`, {
      timeout: 120000,
      stdio: "pipe",
    });
  }
}

/**
 * Execute a coding task using the Letta Code SDK.
 *
 * Uses a persistent worker agent with shared blocks from the Letta hierarchy.
 * Skills are copied into the workspace for automatic discovery.
 * Each task gets a fresh conversation via createSession() to isolate context.
 */
async function executeCodingTask(
  task: string,
  workdir: string
): Promise<string> {
  console.log(`Executing task in ${workdir}: "${task.substring(0, 100)}..."`);

  const agentId = await getOrCreateWorker();

  // Copy skills into the workspace so Letta Code discovers them
  copySkillsToWorkspace(workdir);

  const session = createSession(agentId, {
    cwd: workdir,
    permissionMode: "bypassPermissions",
    disallowedTools: ["AskUserQuestion"],
    skillSources: ["project"],
  });

  try {
    await session.send(task);

    let resultText = "Task completed successfully.";
    for await (const msg of session.stream()) {
      if (msg.type === "result") {
        resultText = msg.result || resultText;
        break;
      }
    }

    return resultText;
  } finally {
    session.close();
  }
}

// =============================================================================
// Express Routes
// =============================================================================

/**
 * POST /code
 *
 * Execute a coding task. Optionally clones a repo first.
 *
 * Body:
 *   - repoUrl (optional): Git URL to clone
 *   - task (required): Description of the coding task
 *   - branch (optional): Branch to checkout (default: default branch)
 *
 * Returns:
 *   - success: boolean
 *   - result: string (on success)
 *   - error: string (on failure)
 *   - duration_ms: number
 */
app.post("/code", async (req: Request, res: Response<CodeResponse>) => {
  const startTime = Date.now();
  const { repoUrl, task, branch } = req.body as CodeRequest;

  if (!task) {
    return res.status(400).json({
      success: false,
      error: "Missing required field: task",
    });
  }

  // Create ephemeral workspace
  let workdir: string | null = null;

  try {
    // Ensure workspace root exists
    if (!existsSync(WORKSPACE_ROOT)) {
      mkdirSync(WORKSPACE_ROOT, { recursive: true });
    }

    workdir = mkdtempSync(path.join(WORKSPACE_ROOT, "session-"));
    console.log(`Created workspace: ${workdir}`);

    // Clone repo if URL provided
    let taskWorkdir = workdir;
    if (repoUrl) {
      const repoDir = path.join(workdir, "repo");
      cloneRepo(repoUrl, repoDir, branch);
      taskWorkdir = repoDir;
    }

    // Execute the coding task with timeout
    const result = await Promise.race([
      executeCodingTask(task, taskWorkdir),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("Task timeout exceeded")), TASK_TIMEOUT_MS)
      ),
    ]);

    const duration_ms = Date.now() - startTime;
    console.log(`Task completed in ${duration_ms}ms`);

    return res.json({
      success: true,
      result,
      duration_ms,
    });
  } catch (error) {
    const duration_ms = Date.now() - startTime;
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`Task failed after ${duration_ms}ms:`, errorMessage);

    return res.status(500).json({
      success: false,
      error: errorMessage,
      duration_ms,
    });
  } finally {
    // Cleanup ephemeral workspace
    if (workdir && existsSync(workdir)) {
      try {
        rmSync(workdir, { recursive: true, force: true });
        console.log(`Cleaned up workspace: ${workdir}`);
      } catch (cleanupError) {
        console.error(`Failed to cleanup workspace ${workdir}:`, cleanupError);
      }
    }
  }
});

/**
 * GET /health
 *
 * Health check endpoint for Docker/Kubernetes probes.
 */
app.get("/health", (_req: Request, res: Response) => {
  res.json({
    status: "healthy",
    timestamp: new Date().toISOString(),
    workerId: codingWorkerId || "not yet created",
  });
});

/**
 * GET /
 *
 * Basic info endpoint.
 */
app.get("/", (_req: Request, res: Response) => {
  res.json({
    service: "coding-sandbox",
    version: "2.0.0",
    endpoints: {
      "POST /code": "Execute a coding task",
      "GET /health": "Health check",
    },
    worker: {
      agentId: codingWorkerId || "not yet created",
      lettaServer: LETTA_BASE_URL,
    },
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Coding sandbox service listening on port ${PORT}`);
  console.log(`Workspace root: ${WORKSPACE_ROOT}`);
  console.log(`Task timeout: ${TASK_TIMEOUT_MS}ms`);
  console.log(`Letta server: ${LETTA_BASE_URL}`);
  console.log(`Skills source: ${SKILLS_SOURCE}`);

  // Pre-discover shared blocks (non-blocking)
  discoverSharedBlocks().then((blocks) => {
    sharedBlocks = blocks;
    console.log("Shared blocks discovered at startup");
  }).catch((error) => {
    console.warn("Could not pre-discover shared blocks:", error);
  });
});
