"""multitenant_config — Multi-tenant Config & Feature Flags for B2B SaaS."""

from .audit import AuditEntry, AuditHandler, AuditLog, print_handler
from .config import ConfigDefinition, TenantConfigOverride
from .exceptions import (
    ConfigNotFoundError,
    FlagNotFoundError,
    MultiTenantConfigError,
    RolloutStrategyError,
    StorageError,
    TenantInactiveError,
    TenantNotFoundError,
    ValidationError,
)
from .flags import FlagDefinition, TenantFlagOverride
from .manager import MultiTenantConfig
from .rollout import (
    AlwaysOffRollout,
    AlwaysOnRollout,
    AndRollout,
    OrRollout,
    PercentageRollout,
    RolloutStrategy,
    ScheduledRollout,
    TenantListRollout,
    UserListRollout,
    rollout_from_dict,
    rollout_to_dict,
)
from .storage import FileStorage, InMemoryStorage, StorageBackend
from .tenant import Tenant, TenantContext

__all__ = [
    # Main class
    "MultiTenantConfig",
    # Tenant
    "Tenant",
    "TenantContext",
    # Rollout strategies
    "RolloutStrategy",
    "AlwaysOnRollout",
    "AlwaysOffRollout",
    "PercentageRollout",
    "UserListRollout",
    "TenantListRollout",
    "ScheduledRollout",
    "AndRollout",
    "OrRollout",
    "rollout_from_dict",
    "rollout_to_dict",
    # Models
    "FlagDefinition",
    "TenantFlagOverride",
    "ConfigDefinition",
    "TenantConfigOverride",
    # Audit
    "AuditLog",
    "AuditEntry",
    "AuditHandler",
    "print_handler",
    # Storage
    "StorageBackend",
    "InMemoryStorage",
    "FileStorage",
    # Exceptions
    "MultiTenantConfigError",
    "TenantNotFoundError",
    "TenantInactiveError",
    "FlagNotFoundError",
    "ConfigNotFoundError",
    "ValidationError",
    "StorageError",
    "RolloutStrategyError",
]

__version__ = "0.1.0"
