"""In-memory storage backend — the default, suitable for tests and dev."""
from __future__ import annotations

import copy
import threading
from typing import Any

from .base import StorageBackend


class InMemoryStorage(StorageBackend):
    """All data stored in nested dicts, protected by an RLock."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tenants: dict[str, dict[str, Any]] = {}
        self._flags: dict[str, dict[str, Any]] = {}
        self._tenant_flags: dict[str, dict[str, dict[str, Any]]] = {}  # [tid][fname]
        self._configs: dict[str, dict[str, Any]] = {}
        self._tenant_configs: dict[str, dict[str, dict[str, Any]]] = {}  # [tid][key]

    # ------------------------------------------------------------------
    # Tenant
    # ------------------------------------------------------------------

    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._tenants.get(tenant_id)
            return copy.deepcopy(data) if data else None

    def save_tenant(self, tenant_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._tenants[tenant_id] = copy.deepcopy(data)

    def list_tenant_ids(self) -> list[str]:
        with self._lock:
            return list(self._tenants)

    def delete_tenant(self, tenant_id: str) -> None:
        with self._lock:
            self._tenants.pop(tenant_id, None)

    # ------------------------------------------------------------------
    # Flag definitions
    # ------------------------------------------------------------------

    def get_flag(self, flag_name: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._flags.get(flag_name)
            return copy.deepcopy(data) if data else None

    def save_flag(self, flag_name: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._flags[flag_name] = copy.deepcopy(data)

    def list_flag_names(self) -> list[str]:
        with self._lock:
            return list(self._flags)

    def delete_flag(self, flag_name: str) -> None:
        with self._lock:
            self._flags.pop(flag_name, None)

    # ------------------------------------------------------------------
    # Tenant flag overrides
    # ------------------------------------------------------------------

    def get_tenant_flag(self, tenant_id: str, flag_name: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._tenant_flags.get(tenant_id, {}).get(flag_name)
            return copy.deepcopy(data) if data else None

    def save_tenant_flag(self, tenant_id: str, flag_name: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._tenant_flags.setdefault(tenant_id, {})[flag_name] = copy.deepcopy(data)

    def list_tenant_flag_names(self, tenant_id: str) -> list[str]:
        with self._lock:
            return list(self._tenant_flags.get(tenant_id, {}))

    def delete_tenant_flag(self, tenant_id: str, flag_name: str) -> None:
        with self._lock:
            self._tenant_flags.get(tenant_id, {}).pop(flag_name, None)

    # ------------------------------------------------------------------
    # Config definitions
    # ------------------------------------------------------------------

    def get_config(self, config_key: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._configs.get(config_key)
            return copy.deepcopy(data) if data else None

    def save_config(self, config_key: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._configs[config_key] = copy.deepcopy(data)

    def list_config_keys(self) -> list[str]:
        with self._lock:
            return list(self._configs)

    def delete_config(self, config_key: str) -> None:
        with self._lock:
            self._configs.pop(config_key, None)

    # ------------------------------------------------------------------
    # Tenant config overrides
    # ------------------------------------------------------------------

    def get_tenant_config(self, tenant_id: str, config_key: str) -> dict[str, Any] | None:
        with self._lock:
            data = self._tenant_configs.get(tenant_id, {}).get(config_key)
            return copy.deepcopy(data) if data else None

    def save_tenant_config(self, tenant_id: str, config_key: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._tenant_configs.setdefault(tenant_id, {})[config_key] = copy.deepcopy(data)

    def list_tenant_config_keys(self, tenant_id: str) -> list[str]:
        with self._lock:
            return list(self._tenant_configs.get(tenant_id, {}))

    def delete_tenant_config(self, tenant_id: str, config_key: str) -> None:
        with self._lock:
            self._tenant_configs.get(tenant_id, {}).pop(config_key, None)
