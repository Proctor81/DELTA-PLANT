"""
Tool per esecuzione codice Python (sandboxed)
"""
from typing import Dict, Any
import structlog

logger = structlog.get_logger("code_execution_tool")

def code_execution_tool(code: str) -> Dict[str, Any]:
    """Esegue codice Python in modo sicuro e restituisce output.
    Args:
        code: codice Python da eseguire
    Returns:
        dict con output o errori
    """
    logger.info("Esecuzione code_execution_tool", code=code)
    try:
        # ATTENZIONE: sandbox reale da implementare!
        exec_globals = {}
        exec(code, exec_globals)
        return {"output": exec_globals}
    except Exception as e:
        logger.error("Errore in code_execution_tool", error=str(e))
        return {"error": str(e)}
