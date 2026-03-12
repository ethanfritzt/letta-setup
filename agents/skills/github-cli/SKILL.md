---
name: github-cli
description: >
  GitHub CLI (gh) patterns for issue management and pull request creation.
  Use when working with GitHub issues, creating pull requests, managing
  branches, reviewing PRs, or any git/GitHub operations. Covers authentication,
  PR deduplication, branch conventions, and issue workflows.
compatibility: Requires gh CLI authenticated via GH_TOKEN environment variable
allowed-tools: Bash(gh:*) Bash(git:*)
---

# GitHub CLI Skill

## Authentication

The `gh` CLI is pre-authenticated via the `GH_TOKEN` environment variable.

```bash
# Verify authentication status
gh auth status

# The git credential helper is already configured via:
# gh auth setup-git --hostname github.com
```

Do NOT attempt to run `gh auth login` interactively. If `gh auth status` fails,
report the error and stop.

## Pull Request Creation

### MANDATORY: Check Before Creating

Before creating ANY pull request, you MUST check for existing PRs that address
the same issue. Skipping this step leads to duplicate PRs.

```bash
# Check by issue number (both search patterns)
gh pr list --search "fixes #<NUMBER>" --repo <OWNER>/<REPO>
gh pr list --search "#<NUMBER>" --repo <OWNER>/<REPO>

# Check for PRs referencing the issue in title
gh pr list --search "<NUMBER>" --repo <OWNER>/<REPO>
```

If ANY existing PR addresses the issue:
- **STOP** - do not create another PR
- Report: "SKIPPED: Issue #N already has PR #M (URL)"
- Move on to the next issue if there are more

### One PR Per Issue

- NEVER combine multiple issues into a single PR
- Each issue gets its own branch and its own PR
- If asked to fix multiple issues, process them sequentially, one at a time
- After completing each PR, check the next issue for existing PRs before starting

### Branch Naming

```bash
# Format: fix/issue-<number>-<short-description>
git checkout -b fix/issue-42-null-pointer-auth

# For features:
git checkout -b feat/issue-15-add-dark-mode
```

Always branch from the repository's default branch:

```bash
# Ensure you're on the default branch first
git checkout main  # or master, depending on repo
git pull origin main
git checkout -b fix/issue-42-description
```

### Commit Messages

```bash
# Format: <type>: <description> (fixes #<number>)
git commit -m "fix: handle null pointer in auth module (fixes #42)"
git commit -m "feat: add dark mode toggle (fixes #15)"
```

Types: `fix`, `feat`, `docs`, `refactor`, `test`, `chore`

### Creating the PR

```bash
# Push the branch
git push -u origin fix/issue-42-null-pointer-auth

# Create PR with explicit title and body
gh pr create \
  --repo <OWNER>/<REPO> \
  --title "Fix #42: Handle null pointer in auth module" \
  --body "Fixes #42

## Changes
- <brief description of what was changed>
- <another change>

## Testing
- <how this was tested>"
```

**Important:** Always include `Fixes #<number>` in the PR body. This auto-closes
the issue when the PR is merged.

### After Creating a PR

Report the result clearly:

```
CREATED: PR #<number> (<url>)
  Issue: #<issue_number>
  Branch: fix/issue-<number>-<description>
  Changes: <brief summary>
```

## Issue Analysis

```bash
# View full issue details
gh issue view <NUMBER> --repo <OWNER>/<REPO>

# View issue as JSON (for parsing labels, assignees, etc.)
gh issue view <NUMBER> --repo <OWNER>/<REPO> --json title,body,labels,assignees

# List issues by label
gh issue list --repo <OWNER>/<REPO> --label "good first issue"
gh issue list --repo <OWNER>/<REPO> --label "bug"

# List open issues
gh issue list --repo <OWNER>/<REPO> --state open
```

## Multi-Issue Workflow

When asked to fix multiple issues:

1. **Analyze all issues first** - read each issue, check for existing PRs
2. **Report findings** - which issues are open, which already have PRs
3. **Process sequentially** - one issue at a time, one PR at a time
4. **Report after each** - status update after each PR created/skipped
5. **Final summary** - total PRs created, total skipped, any failures

Example summary format:

```
Results:
- Issue #10: CREATED PR #101 (https://github.com/org/repo/pull/101)
- Issue #11: CREATED PR #102 (https://github.com/org/repo/pull/102)
- Issue #12: SKIPPED - already has PR #99
```

## Repository Operations

```bash
# Clone a repository
gh repo clone <OWNER>/<REPO>

# Fork and clone
gh repo fork <OWNER>/<REPO> --clone

# View repo info
gh repo view <OWNER>/<REPO>
```

## Common Patterns

```bash
# Check CI status on a PR
gh pr checks <PR_NUMBER> --repo <OWNER>/<REPO>

# View PR diff
gh pr diff <PR_NUMBER> --repo <OWNER>/<REPO>

# List recent PRs
gh pr list --repo <OWNER>/<REPO> --limit 10

# Search issues
gh issue list --repo <OWNER>/<REPO> --search "keyword"
```

## Error Handling

- **Authentication failure**: Report that GH_TOKEN may be invalid or missing
- **Push rejected**: Check if branch already exists, use a different name
- **PR creation failed**: Check if a PR already exists from this branch
- **Rate limited**: Wait and retry, or report the rate limit to the user
- **Permission denied**: Report that the token may lack required scopes (needs `repo` scope)
