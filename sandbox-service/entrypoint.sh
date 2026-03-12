#!/bin/bash
set -e

# Configure GitHub CLI authentication if token is provided.
# This enables:
#   - gh repo clone owner/repo (private repos)
#   - git clone https://github.com/owner/repo (via gh credential helper)
#   - gh pr create, gh issue, etc.
if [ -n "$GH_TOKEN" ]; then
  echo "Configuring GitHub CLI authentication..."
  # Configure git to use gh as the credential helper for github.com
  # The --force flag allows setup without interactive login
  gh auth setup-git --hostname github.com --force
  echo "GitHub authentication configured successfully"
else
  echo "Warning: GH_TOKEN not set - private repo access will not work"
fi

# Copy skills into workspace root so they're available to all sessions.
# Letta Code discovers project-scoped skills from .skills/ relative to cwd.
# Each session workspace inherits these via the sandbox service.
SKILLS_DIR="${SKILLS_SOURCE:-/app/skills}"
if [ -d "$SKILLS_DIR" ]; then
  mkdir -p "${WORKSPACE_ROOT:=/workspace}/.skills"
  cp -r "$SKILLS_DIR"/* "$WORKSPACE_ROOT/.skills/" 2>/dev/null || true
  echo "Copied skills from $SKILLS_DIR to $WORKSPACE_ROOT/.skills/"
else
  echo "No skills directory found at $SKILLS_DIR"
fi

# Execute the main command (npm start)
exec "$@"
