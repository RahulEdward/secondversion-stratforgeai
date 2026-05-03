"""Ollama binary + daemon management subpackage.

The :class:`OllamaManager` owns the lifecycle of the local Ollama binary:
download, process spawn, health checks, stop, uninstall. Provider code reads
the live ``base_url`` from it so model calls always hit the currently-running
instance.
"""
from .manager import OllamaManager, get_manager, init_manager

__all__ = ["OllamaManager", "get_manager", "init_manager"]
