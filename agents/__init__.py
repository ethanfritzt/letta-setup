"""
Letta Agents Package

Usage:
    from agents import create_all_agents
    agent_ids = create_all_agents()

Or run directly:
    python -m agents.create_all
"""

from .create_all import create_all_agents
from .config import get_config, get_client, AgentConfig

__all__ = [
    "create_all_agents",
    "get_config",
    "get_client",
    "AgentConfig",
]
