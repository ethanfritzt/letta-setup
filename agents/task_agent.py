"""
Task Agent - Automation and task management specialist.

Handles to-dos, reminders, structured workflows, and
multi-step automation tasks.
"""

from letta_client import Letta

from .config import AgentConfig


PERSONA = """
You are a task and automation specialist. You help manage to-dos, reminders, and 
structured workflows. When given a task by the Personal Assistant, you execute it 
methodically and report back with a clear result. You keep a running list of any 
ongoing tasks in your archival memory.
""".strip()

HUMAN = "You are being invoked as a subagent. The task will be in the message."


def create_task_agent(client: Letta, config: AgentConfig):
    """
    Create the Task Agent.

    Args:
        client: Letta client instance
        config: Agent configuration (model, embedding, etc.)

    Returns:
        The created agent object
    """
    agent = client.agents.create(
        name="TaskAgent",
        model=config.model,
        embedding=config.embedding,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        tools=["web_search"],  # Extend with custom tools later (e.g. calendar API)
    )
    return agent
