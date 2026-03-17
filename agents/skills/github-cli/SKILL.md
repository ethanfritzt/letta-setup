---
name: github-cli
description: >
  GitHub CLI (gh) patterns for repository management. Covers pull requests,
  issues, releases, tags, branches, CI status, code search, and general
  repo operations. Use when working with any GitHub or git operations.
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

**IMPORTANT:** Always use `gh repo clone` instead of `git clone`. The `gh` CLI
authenticates automatically via the `GH_TOKEN` environment variable, which is
required for private repositories and avoids interactive credential prompts that
fail in non-interactive/sandboxed environments. Never use `git clone` for
GitHub repositories.

```bash
# Clone a repository (ALWAYS use gh, never git clone)
gh repo clone <OWNER>/<REPO>

# Clone with additional git flags (e.g., shallow clone)
gh repo clone <OWNER>/<REPO> -- --depth 1

# Fork and clone
gh repo fork <OWNER>/<REPO> --clone

# View repo info
gh repo view <OWNER>/<REPO>
```

## Repository Information

```bash
# View repo details (description, stars, language, default branch)
gh repo view <OWNER>/<REPO>

# View as JSON for parsing
gh repo view <OWNER>/<REPO> --json name,defaultBranchRef,description,languages,stargazerCount

# List repos for an org or user
gh repo list <OWNER> --limit 20
gh repo list <OWNER> --language python --sort updated

# Open repo in browser
gh browse --repo <OWNER>/<REPO>

# View README
gh repo view <OWNER>/<REPO> --json readme --jq '.readme'
```

## Branch Management

```bash
# List remote branches
git branch -r

# List branches with last commit info
git branch -r --sort=-committerdate --format='%(refname:short) %(committerdate:relative) %(subject)'

# Compare branches (commits in feature not in main)
git log main..feature-branch --oneline

# Compare branches (diff summary)
git diff main...feature-branch --stat

# Delete a merged branch (remote)
git push origin --delete <BRANCH_NAME>

# Check if a branch has been merged
git branch -r --merged main
```

## Releases & Tags

```bash
# List releases
gh release list --repo <OWNER>/<REPO> --limit 10

# View a specific release
gh release view <TAG> --repo <OWNER>/<REPO>

# Create a release from a tag
gh release create v1.2.0 \
  --repo <OWNER>/<REPO> \
  --title "v1.2.0" \
  --notes "## Changes
- Feature A
- Bug fix B"

# Create a release with auto-generated notes (from PRs since last release)
gh release create v1.2.0 \
  --repo <OWNER>/<REPO> \
  --generate-notes

# Create a draft release
gh release create v1.2.0 \
  --repo <OWNER>/<REPO> \
  --draft \
  --generate-notes

# Upload assets to a release
gh release upload v1.2.0 ./dist/artifact.tar.gz --repo <OWNER>/<REPO>

# Create and push a tag
git tag -a v1.2.0 -m "Release v1.2.0"
git push origin v1.2.0

# List tags
git tag --sort=-creatordate | head -20
```

## Code Search

```bash
# Search code across GitHub
gh search code "pattern" --repo <OWNER>/<REPO>

# Search issues and PRs
gh search issues "bug" --repo <OWNER>/<REPO> --state open
gh search prs "refactor" --repo <OWNER>/<REPO> --state merged

# Search repos
gh search repos "topic" --language python --sort stars
```

## GitHub Actions / CI

```bash
# List recent workflow runs
gh run list --repo <OWNER>/<REPO> --limit 10

# View a specific run
gh run view <RUN_ID> --repo <OWNER>/<REPO>

# View run logs
gh run view <RUN_ID> --repo <OWNER>/<REPO> --log

# Watch a run in progress
gh run watch <RUN_ID> --repo <OWNER>/<REPO>

# List workflows
gh workflow list --repo <OWNER>/<REPO>

# Trigger a workflow dispatch
gh workflow run <WORKFLOW> --repo <OWNER>/<REPO> --ref main

# Re-run failed jobs
gh run rerun <RUN_ID> --repo <OWNER>/<REPO> --failed
```

## General Workflow

```bash
# Make arbitrary GitHub API calls
gh api repos/<OWNER>/<REPO>/contributors --jq '.[].login'
gh api repos/<OWNER>/<REPO>/languages
gh api repos/<OWNER>/<REPO>/stats/commit_activity

# Manage labels
gh label list --repo <OWNER>/<REPO>
gh label create "priority: high" --color FF0000 --repo <OWNER>/<REPO>

# Create and manage gists
gh gist create file.py --desc "Description" --public
gh gist list

# View notifications
gh api notifications --jq '.[].subject.title'
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

# Get repo default branch name
gh repo view <OWNER>/<REPO> --json defaultBranchRef --jq '.defaultBranchRef.name'

# Count open issues by label
gh issue list --repo <OWNER>/<REPO> --label "bug" --state open --json number --jq 'length'

# List contributors with commit counts
gh api repos/<OWNER>/<REPO>/contributors --jq '.[] | "\(.login): \(.contributions) commits"'
```

## Error Handling

- **Authentication failure**: Report that GH_TOKEN may be invalid or missing
- **Push rejected**: Check if branch already exists, use a different name
- **PR creation failed**: Check if a PR already exists from this branch
- **Rate limited**: Wait and retry, or report the rate limit to the user
- **Permission denied**: Report that the token may lack required scopes (needs `repo` scope)
- **Not found (404)**: Verify the repo name and owner are correct; check if repo is private and token has access
- **Merge conflict**: Report the conflicting files and suggest resolution approach
