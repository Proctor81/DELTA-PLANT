# Tools package for delta_orchestrator

from .registry import registry
from .delta_context_tool import delta_context_tool
from .code_execution_tool import code_execution_tool
from .vision_tool import vision_tool
from .web_search_tool import web_search_tool

# Registra tutti i tool nel registry centrale
registry.register("delta_context_tool", delta_context_tool)
registry.register("code_execution_tool", code_execution_tool)
registry.register("vision_tool", vision_tool)
registry.register("web_search_tool", web_search_tool)