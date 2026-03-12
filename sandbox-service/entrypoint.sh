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

# Execute the main command (npm start)
exec "$@"
