#!/usr/bin/env python3
"""
Letta Agent Setup Script

Creates all agents in the correct order:
  1. Research Agent - deep research via web search
  2. Task Agent - automation, reminders, scheduling
  3. Personal Assistant (orchestrator) - knows you, delegates to subagents

Run once to create agents, then save the printed IDs for your Discord bot.

Usage:
    python -m agents.create_all
    # or
    python agents/create_all.py

Environment variables:
    LETTA_BASE_URL  - Letta server URL (default: http://localhost:8283)
    LETTA_MODEL     - LLM model (default: anthropic/claude-sonnet-4-6)
    LETTA_EMBEDDING - Embedding model (default: openai/text-embedding-3-small)
"""

from .config import get_config, get_client
from .research_agent import create_research_agent
from .task_agent import create_task_agent
from .personal_assistant import create_personal_assistant


def create_all_agents():
    """
    Create all agents in the correct dependency order.

    Returns:
        dict: Dictionary with agent IDs keyed by role name
    """
    config = get_config()
    client = get_client(config)

    print(f"Connecting to Letta at {config.base_url}")
    print(f"Using model: {config.model}")
    print(f"Using embedding: {config.embedding}")
    print()

    # 1. Create Research Agent first (PA depends on its ID)
    research_agent = create_research_agent(client, config)
    print(f"Research Agent created:      {research_agent.id}")

    # 2. Create Task Agent (PA depends on its ID)
    task_agent = create_task_agent(client, config)
    print(f"Task Agent created:          {task_agent.id}")

    # 3. Create Personal Assistant (depends on both subagent IDs)
    personal_assistant = create_personal_assistant(
        client,
        config,
        research_agent_id=research_agent.id,
        task_agent_id=task_agent.id,
    )
    print(f"Personal Assistant created:  {personal_assistant.id}")

    # Summary output
    print()
    print("-" * 50)
    print("Save these IDs for your Discord bot:")
    print(f'  PERSONAL_ASSISTANT_ID = "{personal_assistant.id}"')
    print(f'  RESEARCH_AGENT_ID     = "{research_agent.id}"')
    print(f'  TASK_AGENT_ID         = "{task_agent.id}"')
    print("-" * 50)

    return {
        "personal_assistant": personal_assistant.id,
        "research_agent": research_agent.id,
        "task_agent": task_agent.id,
    }


if __name__ == "__main__":
    create_all_agents()
