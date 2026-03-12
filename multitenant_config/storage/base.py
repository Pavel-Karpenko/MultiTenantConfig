"""Abstract storage backend interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class StorageBackend(ABC):
    """All data is passed as plain dicts (JSON-serialisable).

    Implementations must be thread-safe.
    """

    # ------------------------------------------------------------------
    # Tenant
    # ------------------------------------------------------------------

    @abstractmethod
    def get_tenant(self, tenant_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_tenant(self, tenant_id: str, data: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_tenant_ids(self) -> list[str]: ...

    @abstractmethod
    def delete_tenant(self, tenant_id: str) -> None: ...

    # ------------------------------------------------------------------
    # Flag definitions (global)
    # ------------------------------------------------------------------

    @abstractmethod
    def get_flag(self, flag_name: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_flag(self, flag_name: str, data: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_flag_names(self) -> list[str]: ...

    @abstractmethod
    def delete_flag(self, flag_name: str) -> None: ...

    # ------------------------------------------------------------------
    # Tenant flag overrides
    # ------------------------------------------------------------------

    @abstractmethod
    def get_tenant_flag(self, tenant_id: str, flag_name: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_tenant_flag(self, tenant_id: str, flag_name: str, data: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_tenant_flag_names(self, tenant_id: str) -> list[str]: ...

    @abstractmethod
    def delete_tenant_flag(self, tenant_id: str, flag_name: str) -> None: ...

    # ------------------------------------------------------------------
    # Config definitions (global)
    # ------------------------------------------------------------------

    @abstractmethod
    def get_config(self, config_key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_config(self, config_key: str, data: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_config_keys(self) -> list[str]: ...

    @abstractmethod
    def delete_config(self, config_key: str) -> None: ...

    # ------------------------------------------------------------------
    # Tenant config overrides
    # ------------------------------------------------------------------

    @abstractmethod
    def get_tenant_config(self, tenant_id: str, config_key: str) -> dict[str, Any] | None: ...

    @abstractmethod
    def save_tenant_config(self, tenant_id: str, config_key: str, data: dict[str, Any]) -> None: ...

    @abstractmethod
    def list_tenant_config_keys(self, tenant_id: str) -> list[str]: ...

    @abstractmethod
    def delete_tenant_config(self, tenant_id: str, config_key: str) -> None: ...
