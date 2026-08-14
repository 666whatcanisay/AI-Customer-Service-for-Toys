"""C-owned fixed reply rule governance.

This package reuses the existing C database, IAM and reviewed knowledge
material lifecycle.  Publishing to A is deliberately left to the next task
card.
"""

from .routes import router

__all__ = ["router"]
