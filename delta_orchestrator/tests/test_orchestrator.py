"""
Test base per DELTA Orchestrator
"""
import pytest
import asyncio
from delta_orchestrator.integration.delta_bridge import orchestrate_task

@pytest.mark.asyncio
async def test_orchestrate_task():
    result = await orchestrate_task("Diagnosi pianta", {"delta_context": {"plant_type": "pomodoro"}})
    assert "confidence" in result
