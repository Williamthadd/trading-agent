"""Backend API for running TradingAgents analyses.

The FastAPI application itself lives in :mod:`tradingagents.webapp.main`.
Keeping this module light avoids constructing the storage backend merely by
importing :mod:`tradingagents.webapp` from another Python process.
"""

__all__ = ["__version__"]

__version__ = "1.0.0"
