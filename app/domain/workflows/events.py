"""SSE event types for the crawl streaming endpoint."""

from __future__ import annotations

from typing import Any


def log_event(message: str) -> dict[str, Any]:
    return {"event": "log", "data": {"message": message}}


def phase_event(phase: str, flow_name: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"phase": phase}
    if flow_name:
        d["flow_name"] = flow_name
    return {"event": "phase", "data": d}


def brand_event(brand_dict: dict[str, Any]) -> dict[str, Any]:
    return {"event": "brand", "data": brand_dict}


def agent_thought_event(
    step: int, thought: str, flow_index: int | None = None
) -> dict[str, Any]:
    d: dict[str, Any] = {"step": step, "thought": thought}
    if flow_index is not None:
        d["flow_index"] = flow_index
    return {"event": "agent_thought", "data": d}


def screenshot_event(
    step: int, data_b64: str, flow_index: int | None = None
) -> dict[str, Any]:
    d: dict[str, Any] = {"step": step, "data_b64": data_b64}
    if flow_index is not None:
        d["flow_index"] = flow_index
    return {"event": "screenshot", "data": d}


def workflow_event(index: int, workflow_dict: dict[str, Any]) -> dict[str, Any]:
    return {"event": "workflow", "data": {"index": index, "workflow": workflow_dict}}


def done_event() -> dict[str, Any]:
    return {"event": "done", "data": {}}


def error_event(message: str) -> dict[str, Any]:
    return {"event": "error", "data": {"message": message}}
