"""Trace backends for persisting execution traces."""

from agent_framework.backends.base import TraceBackend
from agent_framework.backends.jsonl import JsonlBackend

__all__ = ["TraceBackend", "JsonlBackend"]
