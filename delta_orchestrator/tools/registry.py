"""
Registry dei tool per DELTA Orchestrator
"""
from typing import Dict, Callable

class ToolRegistry:
    """Registry centralizzato per tool disponibili nell'orchestrator."""
    def __init__(self):
        self._tools: Dict[str, Callable] = {}

    def register(self, name: str, tool: Callable):
        self._tools[name] = tool

    def get(self, name: str) -> Callable:
        return self._tools[name]

    def all(self) -> Dict[str, Callable]:
        return self._tools

registry = ToolRegistry()
