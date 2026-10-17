"""
Biomni Tool Adapter for ClawAgents Engine.
Dynamically bridges Biomni 180+ domain tools into ClawAgents Tool protocol.
"""

import asyncio
import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

# Ensure biomni is in sys.path across repo, cwd, or LIGASE_BIOMNI_PATH
_pkg_root = Path(__file__).resolve().parent.parent
for _candidate in [
    Path(os.environ["LIGASE_BIOMNI_PATH"]) if os.environ.get("LIGASE_BIOMNI_PATH") else None,
    _pkg_root / "biomni",
    _pkg_root.parent / "biomni",
    Path.cwd() / "biomni",
]:
    if _candidate and _candidate.exists() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from clawagents.tools.registry import ToolResult, Tool, format_tool_error

# Modules whose import failed on the last load, e.g. {"genomics": "No module named 'esm'"}.
# `ligase doctor` reports these so a missing optional dependency is visible, not silent.
SKIPPED_MODULES: Dict[str, str] = {}

# Cache per-module loaded tools to avoid expensive repeated imports
_MODULE_TOOLS_CACHE: Dict[str, List["BiomniTool"]] = {}
_MODULE2API_CACHE: Optional[Dict[str, List[Dict[str, Any]]]] = None


def _default_tool_timeout() -> float:
    raw = os.getenv("LIGASE_TOOL_TIMEOUT", "").strip()
    if raw:
        try:
            val = float(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return 120.0


def _map_param_type(t: str) -> str:
    t_lower = str(t).lower()
    if "int" in t_lower:
        return "integer"
    elif "float" in t_lower or "number" in t_lower:
        return "number"
    elif "bool" in t_lower:
        return "boolean"
    elif "list" in t_lower or "array" in t_lower:
        return "array"
    elif "dict" in t_lower or "object" in t_lower:
        return "object"
    return "string"


class BiomniTool:
    """ClawAgents-compatible Tool wrapping a Biomni domain function."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Dict[str, Any]],
        func: Optional[Callable] = None,
        module_name: str = "",
        keywords: Optional[List[str]] = None,
        timeout: Optional[float] = None,
        module_path: Optional[str] = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self._func = func
        self._module_path = module_path
        self.module_name = module_name
        self.keywords = keywords or [module_name, name]
        self.cacheable = False
        self.timeout = timeout if timeout is not None else _default_tool_timeout()
        self._accepts_var_kw: Optional[bool] = None
        self._accepted_params: Optional[Set[str]] = None
        if func is not None:
            self._accepts_var_kw, self._accepted_params = self._inspect_params(func)

    def _ensure_func(self) -> Callable:
        if self._func is None:
            if not self._module_path:
                raise RuntimeError(f"Tool '{self.name}' has no bound function or module_path")
            impl_mod = importlib.import_module(self._module_path)
            if not hasattr(impl_mod, self.name):
                raise AttributeError(f"Module '{self._module_path}' has no function '{self.name}'")
            self._func = getattr(impl_mod, self.name)
        if self._accepts_var_kw is None:
            self._accepts_var_kw, self._accepted_params = self._inspect_params(self._func)
        return self._func

    @staticmethod
    def _inspect_params(func: Callable) -> tuple[bool, Optional[Set[str]]]:
        try:
            sig = inspect.signature(func)
        except (ValueError, TypeError):
            return True, None
        accepts_var_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
        )
        accepted = {
            name
            for name, p in sig.parameters.items()
            if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        }
        return accepts_var_kw, accepted

    def _prepare_args(self, raw_args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        self._ensure_func()
        args = dict(raw_args) if isinstance(raw_args, dict) else {}
        if not self._accepts_var_kw and self._accepted_params is not None:
            args = {k: v for k, v in args.items() if k in self._accepted_params}
        missing = [
            pname
            for pname, pmeta in (self.parameters or {}).items()
            if pmeta.get("required") and pname not in args
        ]
        if missing:
            raise ValueError(f"Missing required parameter(s): {', '.join(missing)}")
        return args

    async def execute(self, args: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            func = self._ensure_func()
            call_args = self._prepare_args(args)
            loop = asyncio.get_running_loop()

            # Execute synchronously in worker thread to prevent event loop blocking
            if inspect.iscoroutinefunction(func):
                coro = func(**call_args)
            else:
                coro = loop.run_in_executor(None, lambda: func(**call_args))

            if self.timeout and self.timeout > 0:
                res = await asyncio.wait_for(coro, timeout=self.timeout)
            else:
                res = await coro

            # Format output
            if isinstance(res, (dict, list)):
                output_str = json.dumps(res, indent=2, default=str)
            else:
                output_str = str(res)

            return ToolResult(success=True, output=output_str)
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output="",
                error=f"Biomni Tool Timeout in {self.name}: exceeded {self.timeout:.1f}s",
            )
        except Exception as e:
            err_msg = format_tool_error(e)
            return ToolResult(success=False, output="", error=f"Biomni Tool Error in {self.name}: {err_msg}")


def _read_biomni_schemas() -> Dict[str, List[Dict[str, Any]]]:
    """Read Biomni tool schema JSONs directly without importing heavy bio packages."""
    for base in [
        Path(os.environ["LIGASE_BIOMNI_PATH"]) if os.environ.get("LIGASE_BIOMNI_PATH") else None,
        _pkg_root / "biomni",
        _pkg_root.parent / "biomni",
        Path.cwd() / "biomni",
    ]:
        if not base:
            continue
        desc_dir = base / "biomni" / "tool" / "tool_description"
        if desc_dir.is_dir():
            out: Dict[str, List[Dict[str, Any]]] = {}
            for p in sorted(desc_dir.glob("*.json")):
                try:
                    out[f"biomni.tool.{p.stem}"] = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    continue
            if out:
                return out
    from biomni.utils import read_module2api

    return read_module2api()


def get_biomni_claw_tools(
    modules: Optional[List[str]] = None,
    exclude_modules: Optional[List[str]] = None,
    *,
    lazy: bool = True,
) -> List[Tool]:
    """
    Load and return Biomni tools wrapped as ClawAgents Tools.

    Args:
        modules: Specific module names to include (e.g. ['database', 'genomics', 'pharmacology', 'literature'])
        exclude_modules: Module names to exclude
        lazy: Defer importing heavy implementation modules until a tool is executed (default: True)
    """
    global _MODULE2API_CACHE
    try:
        if _MODULE2API_CACHE is None:
            _MODULE2API_CACHE = _read_biomni_schemas()
        module2api = _MODULE2API_CACHE
    except Exception as e:
        SKIPPED_MODULES["biomni"] = f"{type(e).__name__}: {e}"
        return []
    SKIPPED_MODULES.pop("biomni", None)

    tools: List[Tool] = []

    for mod_path, api_list in module2api.items():
        mod_short = mod_path.replace("biomni.tool.", "")
        if modules and mod_short not in modules and mod_path not in modules:
            continue
        if exclude_modules and (mod_short in exclude_modules or mod_path in exclude_modules):
            continue

        cache_key = f"{mod_path}:{'lazy' if lazy else 'eager'}"
        if cache_key in _MODULE_TOOLS_CACHE:
            SKIPPED_MODULES.pop(mod_short, None)
            tools.extend(_MODULE_TOOLS_CACHE[cache_key])
            continue

        impl_mod = None
        if not lazy:
            try:
                impl_mod = importlib.import_module(mod_path)
            except Exception as e:
                SKIPPED_MODULES[mod_short] = f"{type(e).__name__}: {e}"
                continue
            SKIPPED_MODULES.pop(mod_short, None)

        mod_tools: List[BiomniTool] = []
        for api_desc in api_list:
            func_name = api_desc.get("name")
            if not func_name:
                continue
            if impl_mod is not None and not hasattr(impl_mod, func_name):
                continue

            func = getattr(impl_mod, func_name) if impl_mod is not None else None
            doc = api_desc.get("description", "")

            params: Dict[str, Dict[str, Any]] = {}
            for req in api_desc.get("required_parameters", []):
                pname = req.get("name")
                if pname:
                    params[pname] = {
                        "type": _map_param_type(req.get("type", "str")),
                        "description": req.get("description", ""),
                        "required": True,
                    }
            for opt in api_desc.get("optional_parameters", []):
                pname = opt.get("name")
                if pname:
                    params[pname] = {
                        "type": _map_param_type(opt.get("type", "str")),
                        "description": opt.get("description", ""),
                        "required": False,
                    }

            biomni_tool = BiomniTool(
                name=func_name,
                description=doc,
                parameters=params,
                func=func,
                module_name=mod_short,
                keywords=[mod_short, func_name.replace("_", " ")],
                module_path=mod_path,
            )
            mod_tools.append(biomni_tool)

        _MODULE_TOOLS_CACHE[cache_key] = mod_tools
        tools.extend(mod_tools)

    return tools
