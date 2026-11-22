"""Coform Python SDK: dashboard management and agentic core execution.

Use Coform or AsyncCoform with dashboard-issued API keys. Graph changes are
explicit and atomic; detach removes an occurrence, delete removes the entity.
"""

from .client import AsyncCoform, Coform
from .config import Configuration
from .errors import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    CoformError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    StreamProtocolError,
    ValidationError,
)
from .graph import (
    ChainStep,
    CreateEntityMutation,
    DeleteEntityMutation,
    EntityRef,
    GraphMutationBuilder,
    GraphMutationRequest,
    Mutation,
    PatchEntityMutation,
    RelationMutation,
    ReplaceCollectionMutation,
    StepDependencyRef,
)
from .models import (
    ContextCompacting,
    HistoryPair,
    InputItem,
    InvocationEvent,
    InvocationResult,
    Outcome,
    StreamMode,
    TrimPastContext,
)
from .streaming import AsyncInvocationStream, InvocationStream

__version__ = "0.1.0"
__all__ = [
    "CreateEntityMutation",
    "PatchEntityMutation",
    "DeleteEntityMutation",
    "RelationMutation",
    "ReplaceCollectionMutation",
    "Mutation",
    "APIConnectionError",
    "APIStatusError",
    "APITimeoutError",
    "AsyncCoform",
    "AsyncInvocationStream",
    "AuthenticationError",
    "ChainStep",
    "Coform",
    "CoformError",
    "Configuration",
    "ContextCompacting",
    "TrimPastContext",
    "ConflictError",
    "EntityRef",
    "GraphMutationBuilder",
    "GraphMutationRequest",
    "HistoryPair",
    "InputItem",
    "InvocationEvent",
    "InvocationResult",
    "InvocationStream",
    "NotFoundError",
    "Outcome",
    "PermissionDeniedError",
    "RateLimitError",
    "StepDependencyRef",
    "StreamMode",
    "StreamProtocolError",
    "ValidationError",
]
