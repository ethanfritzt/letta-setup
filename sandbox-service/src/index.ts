/**
 * Coding Sandbox Service
 *
 * Express server that accepts coding tasks, clones repositories into
 * ephemeral workspaces, and executes them using the Letta Code SDK.
 *
 * Endpoints:
 *   POST /code - Execute a coding task
 *   GET /health - Health check
 */

import express, { Request, Response } from "express";
import { prompt } from "@letta-ai/letta-code-sdk";
import { execSync, spawn } from "child_process";
import { mkdtempSync, rmSync, existsSync } from "fs";
import path from "path";

const app = express();
app.use(express.json({ limit: "10mb" }));

const PORT = process.env.PORT || 3002;
const WORKSPACE_ROOT = process.env.WORKSPACE_ROOT || "/workspace";
const TASK_TIMEOUT_MS = parseInt(process.env.TASK_TIMEOUT_MS || "600000", 10); // 10 min default

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
 */
function cloneRepo(repoUrl: string, targetDir: string, branch?: string): void {
  const args = ["clone", "--depth", "1"];
  if (branch) {
    args.push("-b", branch);
  }
  args.push(repoUrl, targetDir);

  console.log(`Cloning ${repoUrl}${branch ? ` (branch: ${branch})` : ""} into ${targetDir}`);

  execSync(`git ${args.join(" ")}`, {
    timeout: 120000, // 2 min timeout for clone
    stdio: "pipe",
  });
}

/**
 * Execute a coding task using the Letta Code SDK.
 */
async function executeCodingTask(
  task: string,
  workdir: string
): Promise<string> {
  console.log(`Executing task in ${workdir}: "${task.substring(0, 100)}..."`);

  const result = await prompt(task, {
    cwd: workdir,
    permissionMode: "bypassPermissions", // Headless mode - no human approval needed
    disallowedTools: ["AskUserQuestion"], // Can't interact with human in headless mode
  });

  return result.result || "Task completed successfully.";
}

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
      execSync(`mkdir -p ${WORKSPACE_ROOT}`);
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
  res.json({ status: "healthy", timestamp: new Date().toISOString() });
});

/**
 * GET /
 *
 * Basic info endpoint.
 */
app.get("/", (_req: Request, res: Response) => {
  res.json({
    service: "coding-sandbox",
    version: "1.0.0",
    endpoints: {
      "POST /code": "Execute a coding task",
      "GET /health": "Health check",
    },
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Coding sandbox service listening on port ${PORT}`);
  console.log(`Workspace root: ${WORKSPACE_ROOT}`);
  console.log(`Task timeout: ${TASK_TIMEOUT_MS}ms`);
  console.log(`Letta server: ${process.env.LETTA_BASE_URL || "default"}`);
});
