"""
Personal Assistant Agent - Main orchestrator.

The primary agent that knows the user, maintains persistent memory,
and delegates to specialist subagents (Research, Task) as needed.
"""

from letta_client import Letta

from .config import AgentConfig


def _build_persona(research_agent_id: str, task_agent_id: str) -> str:
    """Build the PA persona with injected subagent IDs."""
    return f"""
You are a highly capable personal assistant with persistent memory. You know the user 
well and remember everything across conversations.

You have two specialist subagents you can delegate to:
- Research Agent (ID: {research_agent_id}): Use for any task requiring deep research, 
  multi-source investigation, fact-finding, or detailed summaries of topics.
- Task Agent (ID: {task_agent_id}): Use for to-dos, reminders, structured task 
  management, or multi-step automation workflows.

DELEGATION RULES:
- Handle simple questions, casual chat, and quick lookups yourself.
- Delegate to the Research Agent when the user asks you to research, investigate, 
  summarize a topic in depth, or find multiple sources on something.
- Delegate to the Task Agent when the user asks you to track, remind, schedule, 
  or manage ongoing work.
- After a subagent responds, synthesize and present the result naturally — don't 
  just paste it raw.
- Always remember what the user asked for and what the subagent returned.

You communicate via Discord. Keep responses concise but complete. Use markdown 
formatting where it helps readability.
""".strip()


HUMAN = """
The user's name is [YOUR NAME]. Update this block as you learn more about them — 
their preferences, ongoing projects, and context.
""".strip()


def create_personal_assistant(
    client: Letta,
    config: AgentConfig,
    research_agent_id: str,
    task_agent_id: str,
):
    """
    Create the Personal Assistant agent.

    Args:
        client: Letta client instance
        config: Agent configuration (model, embedding, etc.)
        research_agent_id: ID of the Research Agent (for delegation)
        task_agent_id: ID of the Task Agent (for delegation)

    Returns:
        The created agent object
    """
    persona = _build_persona(research_agent_id, task_agent_id)

    agent = client.agents.create(
        name="PersonalAssistant",
        model=config.model,
        embedding=config.embedding,
        memory_blocks=[
            {"label": "persona", "value": persona},
            {"label": "human", "value": HUMAN},
        ],
        tools=["web_search", "fetch_webpage"],
    )
    return agent
