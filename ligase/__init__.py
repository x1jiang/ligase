"""
Ligase: local-first biomedical research agent.

    from ligase import create_agent
    agent = create_agent(model="gpt-5.6-luna")
    print(agent.go("What chromosome is APOE on?"))
"""

from ligase.agent import create_agent, LigaseAgent
from ligase.tools_adapter import get_biomni_claw_tools
from ligase.local_harness import is_compact_local_model

__version__ = "0.2.0"
__all__ = [
    "create_agent",
    "LigaseAgent",
    "get_biomni_claw_tools",
    "is_compact_local_model",
]
