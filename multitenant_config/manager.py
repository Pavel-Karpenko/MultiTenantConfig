"""MultiTenantConfig — the main entry point for the library."""
from __future__ import annotations

import contextvars
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Iterator

from .audit import AuditEntry, AuditHandler, AuditLog
from .config import ConfigDefinition, TenantConfigOverride
from .exceptions import (
    ConfigNotFoundError,
    FlagNotFoundError,
    TenantInactiveError,
    TenantNotFoundError,
    ValidationError,
)
from .flags import FlagDefinition, TenantFlagOverride
from .rollout import AlwaysOffRollout, AlwaysOnRollout, RolloutStrategy
from .storage.base import StorageBackend
from .storage.memory import InMemoryStorage
from .tenant import Tenant, TenantContext

# Context variable for implicit tenant context (set via `use_context`)
_CTX_VAR: contextvars.ContextVar[TenantContext | None] = contextvars.ContextVar(
    "multitenant_config_ctx", default=None
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MultiTenantConfig:
    """Manage feature flags and config values across multiple tenants.

    Parameters
    ----------
    storage:
        Persistence backend.  Defaults to InMemoryStorage (no persistence).
    audit_handlers:
        Optional list of callables invoked for every audit entry.
    audit_max_entries:
        Maximum audit entries kept in memory.
    """

    def __init__(
        self,
        storage: StorageBackend | None = None,
        audit_handlers: list[AuditHandler] | None = None,
        audit_max_entries: int = 10_000,
    ) -> None:
        self._storage = storage or InMemoryStorage()
        self._audit = AuditLog(max_entries=audit_max_entries, handlers=audit_handlers)
        self._lock = threading.RLock()

    # ==================================================================
    # Context helpers
    # ==================================================================

    @contextmanager
    def use_context(self, ctx: TenantContext) -> Iterator[None]:
        """Set an implicit TenantContext for the duration of the block.

        Useful to avoid passing *ctx* to every call in a request handler:

            with mtc.use_context(TenantContext("acme")):
                mtc.is_enabled("new_ui")
        """
        token = _CTX_VAR.set(ctx)
        try:
            yield
        finally:
            _CTX_VAR.reset(token)

    def _resolve_ctx(self, ctx: TenantContext | None) -> TenantContext:
        resolved = ctx or _CTX_VAR.get()
        if resolved is None:
            raise ValueError(
                "No TenantContext provided. Pass ctx= or use use_context()."
            )
        return resolved

    # ==================================================================
    # Tenant management
    # ==================================================================

    def register_tenant(
        self,
        tenant_id: str,
        *,
        name: str = "",
        plan: str = "free",
        metadata: dict[str, Any] | None = None,
        actor: str | None = None,
    ) -> Tenant:
        """Register a new tenant.  Idempotent: re-registering updates fields."""
        with self._lock:
            existing_data = self._storage.get_tenant(tenant_id)
            tenant = Tenant(
                id=tenant_id,
                name=name,
                plan=plan,
                metadata=metadata or {},
                created_at=Tenant.from_dict(existing_data).created_at
                if existing_data
                else _utcnow(),
                updated_at=_utcnow(),
                is_active=True,
            )
            self._storage.save_tenant(tenant_id, tenant.to_dict())

        action = "tenant.update" if existing_data else "tenant.register"
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action=action,
            entity_type="tenant",
            entity_id=tenant_id,
            old_value=existing_data,
            new_value=tenant.to_dict(),
        )
        return tenant

    def get_tenant(self, tenant_id: str) -> Tenant:
        """Return tenant or raise TenantNotFoundError."""
        data = self._storage.get_tenant(tenant_id)
        if data is None:
            raise TenantNotFoundError(tenant_id)
        return Tenant.from_dict(data)

    def list_tenants(self, *, include_inactive: bool = False) -> list[Tenant]:
        tenants = [
            Tenant.from_dict(d)
            for tid in self._storage.list_tenant_ids()
            if (d := self._storage.get_tenant(tid)) is not None
        ]
        if not include_inactive:
            tenants = [t for t in tenants if t.is_active]
        return tenants

    def deactivate_tenant(self, tenant_id: str, *, actor: str | None = None) -> None:
        """Soft-delete a tenant (keeps data, marks inactive)."""
        with self._lock:
            tenant = self.get_tenant(tenant_id)
            old = tenant.to_dict()
            tenant.is_active = False
            tenant.updated_at = _utcnow()
            self._storage.save_tenant(tenant_id, tenant.to_dict())
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action="tenant.deactivate",
            entity_type="tenant",
            entity_id=tenant_id,
            old_value=old,
            new_value=tenant.to_dict(),
        )

    # ==================================================================
    # Feature flags — definitions
    # ==================================================================

    def define_flag(
        self,
        name: str,
        *,
        description: str = "",
        enabled: bool = False,
        rollout: RolloutStrategy | None = None,
        tags: list[str] | None = None,
        actor: str | None = None,
    ) -> FlagDefinition:
        """Define (or redefine) a global feature flag.

        *enabled* is a convenience shortcut:
          - ``enabled=True``  → AlwaysOnRollout (overrides *rollout*)
          - ``enabled=False`` → AlwaysOffRollout (only when *rollout* is None)

        Pass an explicit *rollout* strategy for granular control.
        """
        if rollout is None:
            rollout = AlwaysOnRollout() if enabled else AlwaysOffRollout()

        with self._lock:
            existing_data = self._storage.get_flag(name)
            now = _utcnow()
            flag = FlagDefinition(
                name=name,
                description=description,
                rollout=rollout,
                tags=tags or [],
                created_at=FlagDefinition.from_dict(existing_data).created_at
                if existing_data
                else now,
                updated_at=now,
            )
            self._storage.save_flag(name, flag.to_dict())

        action = "flag.update" if existing_data else "flag.define"
        self._audit.record(
            actor=actor,
            tenant_id=None,
            action=action,
            entity_type="flag",
            entity_id=name,
            old_value=existing_data,
            new_value=flag.to_dict(),
        )
        return flag

    def get_flag_definition(self, name: str) -> FlagDefinition:
        data = self._storage.get_flag(name)
        if data is None:
            raise FlagNotFoundError(name)
        return FlagDefinition.from_dict(data)

    def list_flags(self) -> list[FlagDefinition]:
        return [
            FlagDefinition.from_dict(d)
            for n in self._storage.list_flag_names()
            if (d := self._storage.get_flag(n)) is not None
        ]

    def delete_flag(self, name: str, *, actor: str | None = None) -> None:
        with self._lock:
            old = self._storage.get_flag(name)
            self._storage.delete_flag(name)
        self._audit.record(
            actor=actor,
            tenant_id=None,
            action="flag.delete",
            entity_type="flag",
            entity_id=name,
            old_value=old,
            new_value=None,
        )

    # ==================================================================
    # Feature flags — evaluation
    # ==================================================================

    def is_enabled(self, flag_name: str, ctx: TenantContext | None = None) -> bool:
        """Return True if *flag_name* is active for the given context.

        Evaluation priority (highest first):
          1. Tenant explicit override (set via set_tenant_flag)
          2. Global flag rollout strategy
          3. FlagNotFoundError if the flag was never defined

        Raises
        ------
        TenantNotFoundError  — tenant not registered
        TenantInactiveError  — tenant is deactivated
        FlagNotFoundError    — flag not defined
        """
        ctx = self._resolve_ctx(ctx)
        self._assert_tenant_active(ctx.tenant_id)

        flag_data = self._storage.get_flag(flag_name)
        if flag_data is None:
            raise FlagNotFoundError(flag_name)

        # Tenant override takes precedence
        override_data = self._storage.get_tenant_flag(ctx.tenant_id, flag_name)
        if override_data is not None:
            override = TenantFlagOverride.from_dict(override_data)
            return override.rollout.is_enabled(flag_name, ctx)

        # Fall through to global rollout
        flag = FlagDefinition.from_dict(flag_data)
        return flag.rollout.is_enabled(flag_name, ctx)

    def get_all_flags(self, ctx: TenantContext | None = None) -> dict[str, bool]:
        """Evaluate all defined flags for *ctx* and return a name → bool map."""
        ctx = self._resolve_ctx(ctx)
        self._assert_tenant_active(ctx.tenant_id)
        return {name: self.is_enabled(name, ctx) for name in self._storage.list_flag_names()}

    # ==================================================================
    # Feature flags — tenant overrides
    # ==================================================================

    def set_tenant_flag(
        self,
        tenant_id: str,
        flag_name: str,
        *,
        enabled: bool | None = None,
        rollout: RolloutStrategy | None = None,
        actor: str | None = None,
    ) -> None:
        """Override the rollout strategy for one tenant.

        Exactly one of *enabled* or *rollout* must be provided:
          - ``enabled=True``  → pin the flag ON for this tenant
          - ``enabled=False`` → pin the flag OFF for this tenant
          - ``rollout=X``     → apply a custom strategy for this tenant
        """
        if enabled is not None and rollout is not None:
            raise ValueError("Provide either 'enabled' or 'rollout', not both.")
        if enabled is None and rollout is None:
            raise ValueError("Provide 'enabled' or 'rollout'.")

        self._assert_tenant_registered(tenant_id)
        flag_data = self._storage.get_flag(flag_name)
        if flag_data is None:
            raise FlagNotFoundError(flag_name)

        if enabled is not None:
            rollout = AlwaysOnRollout() if enabled else AlwaysOffRollout()

        assert rollout is not None
        with self._lock:
            old_data = self._storage.get_tenant_flag(tenant_id, flag_name)
            now = _utcnow()
            override = TenantFlagOverride(
                tenant_id=tenant_id,
                flag_name=flag_name,
                rollout=rollout,
                created_at=TenantFlagOverride.from_dict(old_data).created_at
                if old_data
                else now,
                updated_at=now,
            )
            self._storage.save_tenant_flag(tenant_id, flag_name, override.to_dict())

        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action="flag.set",
            entity_type="flag",
            entity_id=flag_name,
            old_value=old_data,
            new_value=override.to_dict(),
        )

    def reset_tenant_flag(
        self,
        tenant_id: str,
        flag_name: str,
        *,
        actor: str | None = None,
    ) -> None:
        """Remove tenant override — flag falls back to global strategy."""
        with self._lock:
            old_data = self._storage.get_tenant_flag(tenant_id, flag_name)
            self._storage.delete_tenant_flag(tenant_id, flag_name)
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action="flag.reset",
            entity_type="flag",
            entity_id=flag_name,
            old_value=old_data,
            new_value=None,
        )

    # ==================================================================
    # Config — definitions
    # ==================================================================

    def define_config(
        self,
        key: str,
        default: Any,
        *,
        value_type: type | None = None,
        description: str = "",
        secret: bool = False,
        tags: list[str] | None = None,
        actor: str | None = None,
    ) -> ConfigDefinition:
        """Define (or redefine) a global config key."""
        with self._lock:
            existing_data = self._storage.get_config(key)
            now = _utcnow()
            cfg = ConfigDefinition(
                key=key,
                default=default,
                value_type=value_type,
                description=description,
                secret=secret,
                tags=tags or [],
                created_at=ConfigDefinition.from_dict(existing_data).created_at
                if existing_data
                else now,
                updated_at=now,
            )
            # Validate default against type
            cfg.validate(default)
            self._storage.save_config(key, cfg.to_dict())

        action = "config.update" if existing_data else "config.define"
        self._audit.record(
            actor=actor,
            tenant_id=None,
            action=action,
            entity_type="config",
            entity_id=key,
            old_value=existing_data,
            new_value=cfg.to_dict(),
        )
        return cfg

    def get_config_definition(self, key: str) -> ConfigDefinition:
        data = self._storage.get_config(key)
        if data is None:
            raise ConfigNotFoundError(key)
        return ConfigDefinition.from_dict(data)

    def list_configs(self) -> list[ConfigDefinition]:
        return [
            ConfigDefinition.from_dict(d)
            for k in self._storage.list_config_keys()
            if (d := self._storage.get_config(k)) is not None
        ]

    def delete_config(self, key: str, *, actor: str | None = None) -> None:
        with self._lock:
            old = self._storage.get_config(key)
            self._storage.delete_config(key)
        self._audit.record(
            actor=actor,
            tenant_id=None,
            action="config.delete",
            entity_type="config",
            entity_id=key,
            old_value=old,
            new_value=None,
        )

    # ==================================================================
    # Config — evaluation
    # ==================================================================

    def get_config(self, key: str, ctx: TenantContext | None = None) -> Any:
        """Return the effective config value for *ctx*.

        Resolution order:
          1. Tenant-specific override
          2. Global default defined by define_config()

        Raises ConfigNotFoundError if the key was never defined.
        Raises TenantNotFoundError / TenantInactiveError for bad tenants.
        """
        ctx = self._resolve_ctx(ctx)
        self._assert_tenant_active(ctx.tenant_id)

        cfg_data = self._storage.get_config(key)
        if cfg_data is None:
            raise ConfigNotFoundError(key)
        cfg = ConfigDefinition.from_dict(cfg_data)

        override_data = self._storage.get_tenant_config(ctx.tenant_id, key)
        if override_data is not None:
            return TenantConfigOverride.from_dict(override_data).value

        return cfg.default

    def get_all_configs(self, ctx: TenantContext | None = None) -> dict[str, Any]:
        """Return all config values resolved for *ctx*."""
        ctx = self._resolve_ctx(ctx)
        self._assert_tenant_active(ctx.tenant_id)
        return {k: self.get_config(k, ctx) for k in self._storage.list_config_keys()}

    # ==================================================================
    # Config — tenant overrides
    # ==================================================================

    def set_tenant_config(
        self,
        tenant_id: str,
        key: str,
        value: Any,
        *,
        actor: str | None = None,
    ) -> None:
        """Set a per-tenant config value.  Validates against value_type."""
        self._assert_tenant_registered(tenant_id)
        cfg_data = self._storage.get_config(key)
        if cfg_data is None:
            raise ConfigNotFoundError(key)
        cfg = ConfigDefinition.from_dict(cfg_data)
        value = cfg.validate(value)

        with self._lock:
            old_data = self._storage.get_tenant_config(tenant_id, key)
            now = _utcnow()
            override = TenantConfigOverride(
                tenant_id=tenant_id,
                config_key=key,
                value=value,
                created_at=TenantConfigOverride.from_dict(old_data).created_at
                if old_data
                else now,
                updated_at=now,
            )
            self._storage.save_tenant_config(tenant_id, key, override.to_dict())

        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action="config.set",
            entity_type="config",
            entity_id=key,
            old_value=cfg.mask(old_data["value"]) if old_data else None,
            new_value=cfg.mask(value),
        )

    def reset_tenant_config(
        self,
        tenant_id: str,
        key: str,
        *,
        actor: str | None = None,
    ) -> None:
        """Remove tenant override — key falls back to global default."""
        with self._lock:
            old_data = self._storage.get_tenant_config(tenant_id, key)
            self._storage.delete_tenant_config(tenant_id, key)
        self._audit.record(
            actor=actor,
            tenant_id=tenant_id,
            action="config.reset",
            entity_type="config",
            entity_id=key,
            old_value=old_data,
            new_value=None,
        )

    # ==================================================================
    # Audit log
    # ==================================================================

    def get_audit_log(
        self,
        *,
        tenant_id: str | None = None,
        entity_type: str | None = None,
        action: str | None = None,
        actor: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditEntry]:
        """Query the audit log.  Results are newest-first."""
        return self._audit.query(
            tenant_id=tenant_id,
            entity_type=entity_type,
            action=action,
            actor=actor,
            limit=limit,
            offset=offset,
        )

    def add_audit_handler(self, handler: AuditHandler) -> None:
        """Register an additional audit handler at runtime."""
        self._audit.add_handler(handler)

    # ==================================================================
    # Internal helpers
    # ==================================================================

    def _assert_tenant_registered(self, tenant_id: str) -> None:
        data = self._storage.get_tenant(tenant_id)
        if data is None:
            raise TenantNotFoundError(tenant_id)

    def _assert_tenant_active(self, tenant_id: str) -> None:
        data = self._storage.get_tenant(tenant_id)
        if data is None:
            raise TenantNotFoundError(tenant_id)
        if not data.get("is_active", True):
            raise TenantInactiveError(tenant_id)
