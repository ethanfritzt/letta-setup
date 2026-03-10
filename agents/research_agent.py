"""
Research Agent - Deep research specialist.

Handles tasks requiring web search, multi-source investigation,
fact-finding, and detailed topic summaries.
"""

from letta_client import Letta

from .config import AgentConfig


PERSONA = """
You are a deep research specialist. Your job is to thoroughly investigate topics 
using web search and page fetching. You compile well-structured, cited summaries. 
You are called as a subagent by the Personal Assistant — always return a complete, 
actionable report.
""".strip()

HUMAN = "You are being invoked as a subagent. The task will be in the message."


def create_research_agent(client: Letta, config: AgentConfig):
    """
    Create the Research Agent.

    Args:
        client: Letta client instance
        config: Agent configuration (model, embedding, etc.)

    Returns:
        The created agent object
    """
    agent = client.agents.create(
        name="ResearchAgent",
        model=config.model,
        embedding=config.embedding,
        memory_blocks=[
            {"label": "persona", "value": PERSONA},
            {"label": "human", "value": HUMAN},
        ],
        tools=["web_search", "fetch_webpage"],
    )
    return agent
