"""Skills plugin system — auto-discovered, modular capabilities.

Usage::

    from app.skills import registry

    tools = registry.all_tools()
    result = await registry.execute("compute_rsi", {"dataset_id": "...", "period": 14})
"""

from . import registry

__all__ = ["registry"]
