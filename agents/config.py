"""
Shared configuration for Letta agents.

Environment variables (with defaults):
    LETTA_BASE_URL      - Letta server URL (default: http://localhost:8283)
    LETTA_MODEL         - LLM model to use (default: anthropic/claude-sonnet-4-6)
    LETTA_EMBEDDING     - Embedding model (default: openai/text-embedding-3-small)
"""

import os
from dataclasses import dataclass
from letta_client import Letta


@dataclass
class AgentConfig:
    """Configuration shared across all agents."""
    base_url: str
    model: str
    embedding: str


def get_config() -> AgentConfig:
    """Load configuration from environment variables with defaults."""
    return AgentConfig(
        base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"),
        model=os.getenv("LETTA_MODEL", "anthropic/claude-sonnet-4-6"),
        embedding=os.getenv("LETTA_EMBEDDING", "openai/text-embedding-3-small"),
    )


def get_client(config: AgentConfig | None = None) -> Letta:
    """Create a Letta client using the provided or default config."""
    if config is None:
        config = get_config()
    return Letta(base_url=config.base_url)
