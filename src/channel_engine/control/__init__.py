"""Production control plane.

The package root intentionally exports only the execution gate so execution
modules do not import health/adapter dependencies during package initialization.
Domain, service and health types are available from their focused modules.
"""

from .gate import (
    AllowExecutionControlGate,
    ExecutionControlBlocked,
    ExecutionControlGate,
    PersistentExecutionControlGate,
)

__all__ = [
    "AllowExecutionControlGate",
    "ExecutionControlBlocked",
    "ExecutionControlGate",
    "PersistentExecutionControlGate",
]
