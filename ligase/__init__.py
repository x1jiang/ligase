"""
Ligase: local-first biomedical research agent.

    from ligase import create_agent
    agent = create_agent(model="gpt-5.6-luna")
    print(agent.go("What chromosome is APOE on?"))
"""

from typing import TYPE_CHECKING, Any

__version__ = "0.3.3"
__all__ = [
    "create_agent",
    "LigaseAgent",
    "create_biomni_plus_agent",
    "BiomniPlusAgent",
    "BiomniTool",
    "get_biomni_claw_tools",
    "is_compact_local_model",
    "is_gemma_local_model",
]

if TYPE_CHECKING:
    from ligase.agent import (
        BiomniPlusAgent,
        LigaseAgent,
        create_agent,
        create_biomni_plus_agent,
    )
    from ligase.local_harness import is_compact_local_model, is_gemma_local_model
    from ligase.tools_adapter import BiomniTool, get_biomni_claw_tools


def __getattr__(name: str) -> Any:
    if name in {"create_agent", "LigaseAgent", "create_biomni_plus_agent", "BiomniPlusAgent"}:
        from ligase import agent

        return getattr(agent, name)
    if name in {"BiomniTool", "get_biomni_claw_tools"}:
        from ligase import tools_adapter

        return getattr(tools_adapter, name)
    if name in {"is_compact_local_model", "is_gemma_local_model"}:
        from ligase import local_harness

        return getattr(local_harness, name)
    raise AttributeError(f"module 'ligase' has no attribute {name!r}")
