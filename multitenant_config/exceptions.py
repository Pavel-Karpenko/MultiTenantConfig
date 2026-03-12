"""Custom exceptions for multitenant_config."""


class MultiTenantConfigError(Exception):
    """Base exception for all library errors."""


class TenantNotFoundError(MultiTenantConfigError):
    """Raised when a tenant_id is not registered."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"Tenant not found: {tenant_id!r}")
        self.tenant_id = tenant_id


class TenantInactiveError(MultiTenantConfigError):
    """Raised when operating on a deactivated tenant."""

    def __init__(self, tenant_id: str) -> None:
        super().__init__(f"Tenant is inactive: {tenant_id!r}")
        self.tenant_id = tenant_id


class FlagNotFoundError(MultiTenantConfigError):
    """Raised when a feature flag name is not defined."""

    def __init__(self, flag_name: str) -> None:
        super().__init__(f"Feature flag not defined: {flag_name!r}")
        self.flag_name = flag_name


class ConfigNotFoundError(MultiTenantConfigError):
    """Raised when a config key is not defined."""

    def __init__(self, config_key: str) -> None:
        super().__init__(f"Config key not defined: {config_key!r}")
        self.config_key = config_key


class ValidationError(MultiTenantConfigError):
    """Raised when a config value fails type or constraint validation."""


class StorageError(MultiTenantConfigError):
    """Raised when a storage backend operation fails."""


class RolloutStrategyError(MultiTenantConfigError):
    """Raised for invalid rollout strategy configuration."""
