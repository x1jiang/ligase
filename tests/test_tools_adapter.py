"""
Tests for Ligase tools adapter.
"""

import asyncio
import time
from ligase.tools_adapter import BiomniTool, get_biomni_claw_tools


def test_load_database_tools():
    tools = get_biomni_claw_tools(modules=["database"])
    assert len(tools) > 0
    tool_names = [t.name for t in tools]
    assert "query_uniprot" in tool_names or "query_pdb" in tool_names


def test_tool_schema_mapping():
    tools = get_biomni_claw_tools(modules=["database"])
    for t in tools:
        assert hasattr(t, "name")
        assert hasattr(t, "description")
        assert hasattr(t, "parameters")
        assert hasattr(t, "execute")
        assert isinstance(t.parameters, dict)


def test_biomni_tool_strips_unexpected_kwargs_and_validates_required():
    def sample_fn(gene: str, species: str = "human") -> str:
        return f"{gene}:{species}"

    tool = BiomniTool(
        name="sample_fn",
        description="test tool",
        parameters={
            "gene": {"type": "string", "required": True},
            "species": {"type": "string", "required": False},
        },
        func=sample_fn,
        module_name="test",
    )
    res = asyncio.run(tool.execute({"gene": "APOE", "hallucinated_param": 123}))
    assert res.success is True
    assert res.output == "APOE:human"

    missing = asyncio.run(tool.execute({"hallucinated_param": 123}))
    assert missing.success is False
    assert "Missing required parameter" in (missing.error or "")


def test_biomni_tool_timeout():
    def slow_fn(x: int) -> int:
        time.sleep(0.5)
        return x

    tool = BiomniTool(
        name="slow_fn",
        description="slow tool",
        parameters={"x": {"type": "integer", "required": True}},
        func=slow_fn,
        module_name="test",
        timeout=0.1,
    )
    res = asyncio.run(tool.execute({"x": 1}))
    assert res.success is False
    assert "Timeout" in (res.error or "")
